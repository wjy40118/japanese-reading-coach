from __future__ import annotations

import hmac
import json
import os

import streamlit as st

from src.furigana import (
    annotate_japanese,
    annotate_japanese_in_mixed_text,
    furigana_available,
)
from src.llm_analyzer import (
    LocalTransformersAnalyzer,
    local_model_dependencies_available,
)
from src.official_samples import (
    OfficialSampleResource,
    load_official_catalog,
    search_official_samples,
)
from src.rule_analyzer import RuleBasedAnalyzer
from src.samples import load_samples, sample_to_result
from src.schema import AnalysisResult
from src.text_utils import (
    japanese_character_count,
    level_matches,
    split_sentences,
    validate_article,
)


st.set_page_config(
    page_title="日文阅读拆解教练",
    page_icon="読",
    layout="wide",
)

st.markdown(
    """
    <style>
      :root {
        --ink: #173c32;
        --green: #2e6152;
        --coral: #d8644b;
        --gold: #e8b65a;
        --paper: #f7f3ea;
        --muted: #6e7f76;
      }
      .stApp {
        background: var(--paper);
        color: var(--ink);
      }
      [data-testid="stSidebar"] {
        background: #efe8da;
      }
      h1, h2, h3 {
        color: var(--ink);
        letter-spacing: 0.01em;
      }
      h1 {
        font-family: "Noto Serif SC", "Songti SC", serif;
      }
      .hero-kicker {
        color: var(--coral);
        font-size: 0.85rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        margin-bottom: 0.35rem;
      }
      .quote {
        border-left: 4px solid var(--coral);
        padding: 0.55rem 0.85rem;
        margin: 0.45rem 0 0.75rem;
        background: #fffaf1;
        color: #29483f;
        line-height: 2.65;
      }
      .furigana-text {
        line-height: 2.75;
        white-space: pre-wrap;
      }
      .furigana-panel {
        background: #fffaf1;
        border: 1px solid #e3dac8;
        border-radius: 0.8rem;
        padding: 1rem 1.15rem;
        margin: 0.5rem 0 1rem;
      }
      .sentence-block {
        padding: 0.9rem 0 1rem;
        border-bottom: 1px solid #e3dac8;
      }
      .sentence-block:last-child {
        border-bottom: none;
      }
      .knowledge-note {
        color: #c44732;
        font-size: 0.9rem;
        line-height: 2.1;
        margin-top: 0.5rem;
      }
      .knowledge-note strong {
        color: #a93623;
      }
      ruby {
        ruby-position: over;
      }
      rt {
        color: #72847b;
        font-size: 0.52em;
        font-weight: 400;
        letter-spacing: 0.02em;
        line-height: 1.25;
      }
      .small-note {
        color: var(--muted);
        font-size: 0.9rem;
      }
      [data-testid="stMetricValue"] {
        color: var(--green);
      }
    </style>
    """,
    unsafe_allow_html=True,
)


KIND_LABELS = {
    "grammar": "语法",
    "vocabulary": "词汇",
    "structure": "句型",
    "cohesion": "篇章连接",
    "other": "其他",
}
DATA_VERSION = "2026-11-09-official-samples-v6"


def frequency_stars(value: int) -> str:
    value = max(1, min(int(value), 5))
    return "★" * value + "☆" * (5 - value)


def private_password() -> str:
    configured = os.getenv("PRIVATE_APP_PASSWORD", "").strip()
    if configured:
        return configured
    try:
        return str(st.secrets.get("PRIVATE_APP_PASSWORD", "")).strip()
    except Exception:
        return ""


def enforce_private_access() -> bool:
    expected = private_password()
    if not expected:
        return False
    if st.session_state.get("private_authenticated"):
        return True

    st.title("私密访问")
    st.write("该应用包含授权用途的题库或学习资料，请输入访问密码。")
    with st.form("private_access_form"):
        supplied = st.text_input("访问密码", type="password")
        submitted = st.form_submit_button("进入应用", type="primary")
    if submitted:
        if hmac.compare_digest(supplied, expected):
            st.session_state["private_authenticated"] = True
            st.rerun()
        st.error("密码不正确。")
    st.stop()


def logout_private() -> None:
    st.session_state.pop("private_authenticated", None)


@st.cache_data
def get_samples(data_version: str):
    del data_version
    return load_samples()


@st.cache_resource
def get_rule_analyzer(data_version: str) -> RuleBasedAnalyzer:
    del data_version
    return RuleBasedAnalyzer()


@st.cache_data
def get_official_catalog(data_version: str):
    del data_version
    return load_official_catalog()


@st.cache_resource
def get_model_analyzer() -> LocalTransformersAnalyzer:
    return LocalTransformersAnalyzer()


def reset_analysis() -> None:
    st.session_state.pop("analysis", None)
    st.session_state.pop("last_article", None)
    st.session_state.pop("last_analysis_level", None)
    st.session_state.pop("official_sample_id", None)
    st.session_state["show_answers"] = False


def migrate_result(result):
    if result is None:
        return None
    points = getattr(result, "points", [])
    if all(hasattr(point, "exam_frequency") for point in points):
        return result

    if hasattr(result, "to_dict"):
        payload = result.to_dict()
    else:
        payload = dict(result)
    for point in payload.get("points", []):
        point.setdefault("exam_frequency", 3)
        point.setdefault("reading", "")
    return AnalysisResult.from_dict(payload)


def filter_result_by_level(result: AnalysisResult, level: str) -> AnalysisResult:
    original_count = len(result.points)
    result.points = [
        point
        for point in result.points
        if level_matches(point.estimated_level, level)
    ]
    result.estimated_level = level
    if original_count != len(result.points):
        result.warnings.append(
            f"已按所选 {level} 等级筛选，隐藏了 {original_count - len(result.points)} "
            "个其他等级的候选知识点。"
        )
    return result


def enrich_analysis_points(
    result: AnalysisResult,
    article: str,
    analyzer: RuleBasedAnalyzer,
    *,
    level: str,
    focus: list[str],
) -> AnalysisResult:
    supplement = analyzer.analyze(
        article,
        level=level,
        focus=focus,
        max_points=None,
    )
    existing = {(point.kind, point.term) for point in result.points}
    added = 0
    for point in supplement.points:
        key = (point.kind, point.term)
        if key in existing:
            continue
        result.points.append(point)
        existing.add(key)
        added += 1
    if added:
        result.warnings.append(
            f"额外合并了 {added} 个规则或语境词汇候选；"
            "这些候选需要结合上下文核验。"
        )
    result.points.sort(
        key=lambda point: (
            -getattr(point, "exam_frequency", 3),
            -getattr(point, "confidence", 0.0),
            getattr(point, "term", ""),
        )
    )
    return result


def points_for_sentence(sentence: str, points) -> list:
    matched = []
    seen = set()
    for point in points:
        quote = str(getattr(point, "quote", "")).strip()
        term = str(getattr(point, "term", "")).strip()
        if not (
            (quote and (quote in sentence or sentence in quote))
            or (term and term in sentence)
        ):
            continue
        key = (getattr(point, "kind", ""), term)
        if key in seen:
            continue
        matched.append(point)
        seen.add(key)
    return matched


def render_analysis(result: AnalysisResult, article: str) -> None:
    st.divider()
    st.subheader("分析结果")

    first, second, third = st.columns(3)
    first.metric("知识点", len(result.points))
    second.metric("练习", len(result.practice))
    third.metric("估计水平", result.estimated_level)

    if result.mode == "demo":
        st.caption("当前显示的是预存示例分析，适合课堂演示和无模型环境。")
    elif result.mode == "rule":
        st.caption("当前结果由本地规则与候选词典生成；它不是完整语义分析。")
    else:
        st.caption(f"当前结果来自本地开源模型：{result.mode.removeprefix('model:')}")

    tabs = st.tabs(["文章概览", "原文", "知识点", "练习", "导出"])

    with tabs[0]:
        st.markdown("### 文章摘要")
        st.write(result.summary)
        if result.warnings:
            for warning in result.warnings:
                st.warning(warning)

    with tabs[1]:
        st.markdown("### 原文与汉字注音")
        for sentence in split_sentences(article):
            matched_points = points_for_sentence(sentence, result.points)
            notes = []
            for point in matched_points:
                notes.append(
                    f"{KIND_LABELS.get(point.kind, point.kind)}・"
                    f"{annotate_japanese(point.term)} "
                    f"{frequency_stars(getattr(point, 'exam_frequency', 3))}"
                )
            note_html = (
                '<div class="knowledge-note"><strong>知识点：</strong>'
                + "　".join(notes)
                + "</div>"
                if notes
                else ""
            )
            st.markdown(
                '<div class="sentence-block">'
                f'<div class="furigana-text">{annotate_japanese(sentence)}</div>'
                f"{note_html}"
                "</div>",
                unsafe_allow_html=True,
            )

    with tabs[2]:
        if not result.points:
            st.info("没有识别出可展示的知识点。请缩短文章或切换到模型模式。")
        for index, point in enumerate(result.points, start=1):
            with st.container(border=True):
                left, right = st.columns([4, 1])
                with left:
                    st.markdown(
                        f"#### {index}. {annotate_japanese(point.term)}",
                        unsafe_allow_html=True,
                    )
                    if (
                        point.kind == "vocabulary"
                        and not getattr(point, "reading", "").strip()
                    ):
                        st.caption("平假名读音未提供，建议人工核对。")
                with right:
                    st.caption(KIND_LABELS.get(point.kind, point.kind))
                    st.markdown(
                        f"**考频**　"
                        f"{frequency_stars(getattr(point, 'exam_frequency', 3))}"
                    )
                    st.caption("估计值")
                st.markdown(
                    f'<div class="quote">{annotate_japanese(point.quote)}</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    annotate_japanese_in_mixed_text(point.explanation),
                    unsafe_allow_html=True,
                )
                detail_bits = []
                if point.structure:
                    detail_bits.append(
                        f"**结构：** {annotate_japanese(point.structure)}"
                    )
                if point.example:
                    detail_bits.append(
                        f"**例句：** {annotate_japanese(point.example)}"
                    )
                if detail_bits:
                    st.markdown(
                        "  \n".join(detail_bits),
                        unsafe_allow_html=True,
                    )
                st.caption(
                    f"估计难度：{point.estimated_level}　"
                    f"置信度：{point.confidence:.0%}"
                )

    with tabs[3]:
        if not result.practice:
            st.info("这一模式暂未生成练习。示例案例和本地模型模式包含练习题。")
        else:
            for index, question in enumerate(result.practice, start=1):
                st.markdown(
                    f"#### 第 {index} 题　"
                    f"{annotate_japanese_in_mixed_text(question.question)}",
                    unsafe_allow_html=True,
                )
                st.radio(
                    "选择答案",
                    question.options,
                    index=None,
                    key=f"practice_{index}_{len(result.points)}",
                    label_visibility="collapsed",
                )
            if st.button("显示答案与解析", type="secondary"):
                st.session_state["show_answers"] = True
            if st.session_state.get("show_answers"):
                for index, question in enumerate(result.practice, start=1):
                    if question.options:
                        answer = question.options[question.answer_index]
                        st.markdown(
                            "**"
                            f"第 {index} 题答案："
                            f"{annotate_japanese_in_mixed_text(answer)}"
                            "**",
                            unsafe_allow_html=True,
                        )
                    st.markdown(
                        annotate_japanese_in_mixed_text(question.explanation),
                        unsafe_allow_html=True,
                    )

    with tabs[4]:
        payload = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
        st.download_button(
            "下载 JSON 分析结果",
            data=payload,
            file_name="japanese_article_analysis.json",
            mime="application/json",
        )
        st.code(payload, language="json")


def render_bank_analysis(result: BankAnalysis) -> None:
    st.divider()
    year_label = (
        str(result.selected_years[0])
        if len(result.selected_years) == 1
        else "、".join(str(year) for year in result.selected_years)
    )
    st.subheader(f"{year_label}年 {result.level} {result.source_label}分析")

    first, second, third, fourth = st.columns(4)
    first.metric("文章", len(result.articles))
    second.metric("题目", result.total_questions)
    third.metric("汇总知识点", len(result.knowledge_points))
    fourth.metric("知识点练习", len(result.practice))
    st.warning(result.disclaimer)

    tabs = st.tabs(["文章概览", "知识点", "知识点练习", "导出"])

    with tabs[0]:
        overview_rows = []
        for item in result.articles:
            overview_rows.append(
                {
                    "年份": item.entry.get("year", ""),
                    "文章": item.entry.get("title", ""),
                    "水平": item.entry.get("level", ""),
                    "主题": item.entry.get("topic", ""),
                    "题目数": len(item.entry.get("questions", [])),
                    "知识点数": len(item.analysis.points),
                }
            )
        st.dataframe(overview_rows, hide_index=True, width="stretch")

        for item in result.articles:
            entry = item.entry
            title = (
                f"{entry.get('year', '')}｜{entry.get('title', '')}"
                f"｜{len(item.analysis.points)} 个知识点"
            )
            with st.expander(title):
                st.caption(
                    f"水平：{entry.get('level', '')}　"
                    f"主题：{entry.get('topic', '')}"
                )
                st.markdown(
                    f'<div class="furigana-text furigana-panel">'
                    f"{annotate_japanese(str(entry.get('passage', '')))}</div>",
                    unsafe_allow_html=True,
                )
                st.markdown("**阅读题目**")
                for question_index, question in enumerate(
                    entry.get("questions", []),
                    start=1,
                ):
                    st.markdown(
                        f"{question_index}. "
                        f"{annotate_japanese_in_mixed_text(str(question))}",
                        unsafe_allow_html=True,
                    )

    with tabs[1]:
        if not result.knowledge_points:
            st.info("当前筛选条件下没有识别出知识点。")
        for index, point in enumerate(result.knowledge_points, start=1):
            with st.container(border=True):
                left, right = st.columns([4, 1])
                with left:
                    st.markdown(
                        f"#### {index}. {annotate_japanese(point.term)}",
                        unsafe_allow_html=True,
                    )
                with right:
                    st.caption(KIND_LABELS.get(point.kind, point.kind))
                    st.markdown(
                        f"**考频**　{frequency_stars(point.exam_frequency)}"
                    )
                    st.caption("估计值")
                years = "、".join(str(year) for year in point.years)
                st.caption(f"出现于：{years}｜覆盖文章：{len(point.titles)} 篇")
                st.markdown(
                    annotate_japanese_in_mixed_text(point.explanation),
                    unsafe_allow_html=True,
                )
                if point.quotes:
                    st.markdown("**题库原文例句**")
                    for quote in point.quotes[:3]:
                        st.markdown(
                            f'<div class="quote">{annotate_japanese(quote)}</div>',
                            unsafe_allow_html=True,
                        )
                if point.example:
                    st.markdown(
                        f"**补充例句：** {annotate_japanese(point.example)}",
                        unsafe_allow_html=True,
                    )

    with tabs[2]:
        if not result.practice:
            st.info("当前筛选条件下暂未生成知识点练习。")
        else:
            for index, question in enumerate(result.practice, start=1):
                st.markdown(
                    f"#### 第 {index} 题　"
                    f"{annotate_japanese_in_mixed_text(question.question)}",
                    unsafe_allow_html=True,
                )
                st.radio(
                    "选择答案",
                    question.options,
                    index=None,
                    key=f"bank_practice_{index}_{len(result.practice)}",
                    label_visibility="collapsed",
                )
            if st.button("显示题库练习答案", type="secondary"):
                st.session_state["bank_show_answers"] = True
            if st.session_state.get("bank_show_answers"):
                for index, question in enumerate(result.practice, start=1):
                    if question.options:
                        answer = question.options[question.answer_index]
                        st.markdown(
                            "**"
                            f"第 {index} 题答案："
                            f"{annotate_japanese_in_mixed_text(answer)}"
                            "**",
                            unsafe_allow_html=True,
                        )
                    st.markdown(
                        annotate_japanese_in_mixed_text(question.explanation),
                        unsafe_allow_html=True,
                    )

    with tabs[3]:
        payload = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
        st.download_button(
            "下载题库分析 JSON",
            data=payload,
            file_name="exam_bank_analysis.json",
            mime="application/json",
        )
        st.code(payload, language="json")


def go_to_single_analysis() -> None:
    st.session_state["analysis_mode"] = "规则解析"
    st.session_state["article_input"] = ""


def render_official_sample(resource: OfficialSampleResource) -> None:
    st.divider()
    st.subheader(f"{resource.level}｜{resource.collection_label}")
    st.write(resource.description)
    if resource.published_year:
        st.caption(f"官方资料发布年份：{resource.published_year}")
    else:
        st.caption("官方互动样题，不按考试年份逐年发布。")
    st.info(
        "这里仅接入 JLPT 官方公开链接，不复制或重新托管题面。"
        "官方样题不等同于完整历年真题。"
    )

    left, right = st.columns(2)
    with left:
        st.link_button(
            "打开官方样题",
            resource.question_url,
            width="stretch",
        )
    with right:
        if resource.answer_url:
            st.link_button(
                "打开官方答案",
                resource.answer_url,
                width="stretch",
            )
        else:
            st.button(
                "该样题无单独答案文件",
                disabled=True,
                width="stretch",
            )

    st.markdown("**使用方式**")
    st.write(
        "打开官方 PDF 或互动样题，复制其中允许用于学习的阅读正文，"
        "再到“规则解析”中粘贴分析。应用不会自动抓取或保存官方题面。"
    )
    st.button(
        "转到单篇分析",
        type="secondary",
        on_click=go_to_single_analysis,
    )

    with st.expander("来源与版权说明"):
        st.markdown(f"[JLPT 官方样题页面]({resource.source_url})")
        st.markdown(f"[官方版权与使用政策]({resource.policy_url})")

    metadata = {
        "id": resource.id,
        "level": resource.level,
        "collection": resource.collection_label,
        "published_year": resource.published_year,
        "description": resource.description,
        "question_url": resource.question_url,
        "answer_url": resource.answer_url,
        "source_url": resource.source_url,
        "policy_url": resource.policy_url,
        "note": "仅保存官方资源元数据，不包含题面正文。",
    }
    st.download_button(
        "导出官方资源信息",
        data=json.dumps(metadata, ensure_ascii=False, indent=2),
        file_name=f"{resource.id}-official-resource.json",
        mime="application/json",
    )


def main() -> None:
    private_enabled = enforce_private_access()
    st.markdown('<div class="hero-kicker">READING COACH</div>', unsafe_allow_html=True)
    st.title("日文阅读拆解教练")
    st.write(
        "输入一段日语短文，提取语法、词汇和句子结构。每个知识点都保留原文引用，"
        "并附上中文解释和小练习。"
    )

    samples = get_samples(DATA_VERSION)
    analyzer = get_rule_analyzer(DATA_VERSION)
    official_catalog = get_official_catalog(DATA_VERSION)
    model_deps_ready = local_model_dependencies_available()

    with st.sidebar:
        st.header("分析设置")
        if private_enabled:
            st.button(
                "退出私密访问",
                on_click=logout_private,
                width="stretch",
            )
        mode_label = st.radio(
            "分析方式",
            [
                "演示案例",
                "规则解析",
                "本地模型（可选）",
                "官方公开样题",
            ],
            index=0,
            on_change=reset_analysis,
            key="analysis_mode",
        )
        level = st.selectbox(
            "预估水平",
            ["N4", "N3", "N2", "N1"],
            index=1,
        )
        refresh_requested = st.button(
            "刷新",
            help="按当前模式和预估水平重新分析。",
            width="stretch",
        )
        focus = st.multiselect(
            "学习重点",
            ["全部", "语法", "词汇", "句型", "篇章"],
            default=["全部"],
            on_change=reset_analysis,
        )
        st.caption(
            "演示案例完全离线；规则解析无需下载模型；本地模型模式需要额外依赖和显卡。"
        )
        if not furigana_available():
            st.warning(
                "当前环境没有 SudachiPy 词典，无法生成全部汉字注音。"
                "请执行 pip install -r requirements.txt。"
            )
        st.caption("考频星级为基于常见考试与练习的估计值，不是官方统计数据。")
        st.caption("通用分析只显示所选等级；官方样题模式以模式内的考试等级为准。")

    article = ""
    analyze_clicked = False
    official_search_clicked = False
    pending_result = None
    permission = False
    needs_refresh_notice = False
    active_level = level
    matched_official_resource: OfficialSampleResource | None = None

    if mode_label == "官方公开样题":
        official_levels = ["N1", "N2", "N3", "N4", "N5"]
        official_level = st.selectbox(
            "考试等级",
            official_levels,
            index=official_levels.index(level) if level in official_levels else 2,
            on_change=reset_analysis,
        )
        collections = official_catalog["collections"]
        collection_labels = [str(item["label"]) for item in collections]
        selected_collection_label = st.selectbox(
            "资料来源",
            collection_labels,
            index=2 if len(collection_labels) > 2 else 0,
            on_change=reset_analysis,
        )
        selected_collection = collections[
            collection_labels.index(selected_collection_label)
        ]
        active_level = official_level
        official_resource = search_official_samples(
            official_catalog,
            level=official_level,
            collection_id=str(selected_collection["id"]),
        )
        matched_official_resource = official_resource
        st.info(
            "官方公开样题不按考试年份逐年发布，因此这里改为按等级和资料版本检索。"
        )
        if official_resource:
            st.caption(
                f"已匹配：{official_level}｜{official_resource.collection_label}"
            )
        else:
            st.warning(
                f"没有找到 {official_level}｜{selected_collection_label} 的官方资源。"
            )
        official_search_clicked = st.button(
            "查找官方样题",
            type="primary",
            disabled=official_resource is None,
        )
    elif mode_label == "演示案例":
        sample_titles = [f"{item['title']}｜{item['description']}" for item in samples]
        selected_title = st.selectbox(
            "选择示例文章",
            sample_titles,
            on_change=reset_analysis,
        )
        selected_index = sample_titles.index(selected_title)
        sample = samples[selected_index]
        article = sample["article"]
        st.markdown(
            f"### {annotate_japanese(sample['title'])}",
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="furigana-text furigana-panel">'
            f"{annotate_japanese(article)}</div>",
            unsafe_allow_html=True,
        )
        analyze_clicked = st.button("展示预存分析", type="primary")
        pending_result = sample_to_result(sample)
    else:
        if "article_input" not in st.session_state:
            st.session_state["article_input"] = samples[0]["article"]
        article = st.text_area(
            "粘贴日语文章",
            height=260,
            key="article_input",
            placeholder="建议输入 3–8 句，40–1200 个字符。",
        )
        count = japanese_character_count(article)
        st.caption(
            f"当前字符数：{len(article)}　日文字符：{count}　"
            "建议一次分析不超过 1,200 个字符。"
        )
        permission = st.checkbox(
            "我确认这段文章可以用于本次分析，且不包含不应上传的个人敏感信息。"
        )

        if mode_label == "规则解析":
            analyze_clicked = st.button(
                "开始规则分析",
                type="primary",
                disabled=not permission,
            )
        else:
            if not model_deps_ready:
                st.warning(
                    "当前环境尚未安装 torch / transformers / accelerate。"
                    "演示案例和规则解析仍可直接运行。"
                )
            analyze_clicked = st.button(
                "运行本地开源模型",
                type="primary",
                disabled=not permission or not model_deps_ready,
            )

        pending_result = None

    previous_level = st.session_state.get("last_analysis_level")
    if not previous_level:
        previous_result = st.session_state.get("analysis")
        if previous_result is not None:
            previous_level = getattr(previous_result, "estimated_level", "")
    has_previous_result = st.session_state.get("analysis") is not None
    if has_previous_result and previous_level and previous_level != active_level:
        reset_analysis()
        needs_refresh_notice = True

    if refresh_requested:
        reset_analysis()
        if mode_label == "官方公开样题" and matched_official_resource:
            official_search_clicked = True
        elif mode_label == "演示案例":
            analyze_clicked = True
        elif mode_label == "规则解析" and permission:
            analyze_clicked = True
        elif mode_label == "本地模型（可选）" and permission and model_deps_ready:
            analyze_clicked = True
        else:
            needs_refresh_notice = True

    if official_search_clicked and matched_official_resource:
        st.session_state["official_sample_id"] = matched_official_resource.id

    if analyze_clicked:
        st.session_state["show_answers"] = False
        try:
            if mode_label == "演示案例":
                result = pending_result
            elif mode_label == "规则解析":
                validation_error = validate_article(article)
                if validation_error:
                    st.error(validation_error)
                    return
                result = analyzer.analyze(article, level=level, focus=focus)
            else:
                validation_error = validate_article(article)
                if validation_error:
                    st.error(validation_error)
                    return
                with st.spinner("正在加载并运行本地模型，首次加载可能需要几分钟……"):
                    result = get_model_analyzer().analyze(
                        article,
                        level=level,
                        focus=focus,
                    )
            if result is None:
                raise RuntimeError("没有生成分析结果")
            result = filter_result_by_level(result, level)
            result = enrich_analysis_points(
                result,
                article,
                analyzer,
                level=level,
                focus=focus,
            )
            st.session_state["analysis"] = result
            st.session_state["last_analysis_level"] = level
            st.session_state["last_article"] = article
        except Exception as exc:
            st.error(str(exc))
            st.info("可以切换到演示案例或规则解析继续体验。")

    result = migrate_result(st.session_state.get("analysis"))
    if result is not None:
        st.session_state["analysis"] = result
    last_article = st.session_state.get("last_article", article)
    official_result = None
    if (
        matched_official_resource
        and st.session_state.get("official_sample_id")
        == matched_official_resource.id
    ):
        official_result = matched_official_resource
    if (
        needs_refresh_notice
        and not analyze_clicked
        and not official_search_clicked
    ):
        st.info("预估水平或刷新条件已变化，请点击左侧【刷新】重新分析。")
    if official_result:
        render_official_sample(official_result)
    elif result:
        render_analysis(result, last_article)
    else:
        st.info("选择分析模式后，点击对应按钮开始。")

    with st.expander("这个原型如何处理 AI 风险？"):
        st.markdown(
            """
            - 每个知识点必须引用原文，不能只给抽象结论。
            - JLPT 等级只标记为估计值，不代表官方等级。
            - 不为文章自动生成整篇翻译。
            - 信息不足时提示补充文本，而不是强行解释。
            - 用户需要确认文章具有使用权，示例文章使用合成文本。
            """
        )


if __name__ == "__main__":
    main()


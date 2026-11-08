from __future__ import annotations

import json

import streamlit as st

from src.exam_bank import (
    BankAnalysis,
    analyze_exam_bank,
    filter_exam_bank,
    load_exam_bank,
)
from src.furigana import (
    annotate_japanese,
    annotate_japanese_in_mixed_text,
    furigana_available,
)
from src.llm_analyzer import (
    LocalTransformersAnalyzer,
    local_model_dependencies_available,
)
from src.rule_analyzer import RuleBasedAnalyzer
from src.samples import load_samples, sample_to_result
from src.schema import AnalysisResult
from src.text_utils import (
    japanese_character_count,
    level_matches,
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
DATA_VERSION = "2026-11-09-ten-year-bank-v4"


def frequency_stars(value: int) -> str:
    value = max(1, min(int(value), 5))
    return "★" * value + "☆" * (5 - value)


@st.cache_data
def get_samples(data_version: str):
    del data_version
    return load_samples()


@st.cache_resource
def get_rule_analyzer(data_version: str) -> RuleBasedAnalyzer:
    del data_version
    return RuleBasedAnalyzer()


@st.cache_data
def get_exam_bank(data_version: str):
    del data_version
    return load_exam_bank()


@st.cache_resource
def get_model_analyzer() -> LocalTransformersAnalyzer:
    return LocalTransformersAnalyzer()


def reset_analysis() -> None:
    st.session_state.pop("analysis", None)
    st.session_state.pop("bank_analysis", None)
    st.session_state.pop("last_article", None)
    st.session_state.pop("last_analysis_level", None)
    st.session_state["show_answers"] = False
    st.session_state["bank_show_answers"] = False


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

    tabs = st.tabs(["文章概览", "知识点", "练习", "导出"])

    with tabs[0]:
        st.markdown("### 文章摘要")
        st.write(result.summary)
        if result.warnings:
            for warning in result.warnings:
                st.warning(warning)
        with st.expander("查看原文"):
            st.markdown(
                f'<div class="furigana-text">{annotate_japanese(article)}</div>',
                unsafe_allow_html=True,
            )

    with tabs[1]:
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

    with tabs[2]:
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

    with tabs[3]:
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
    st.subheader("近10年模拟阅读题库分析")

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


def main() -> None:
    st.markdown('<div class="hero-kicker">READING COACH</div>', unsafe_allow_html=True)
    st.title("日文阅读拆解教练")
    st.write(
        "输入一段日语短文，提取语法、词汇和句子结构。每个知识点都保留原文引用，"
        "并附上中文解释和小练习。"
    )

    samples = get_samples(DATA_VERSION)
    analyzer = get_rule_analyzer(DATA_VERSION)
    exam_bank = get_exam_bank(DATA_VERSION)
    model_deps_ready = local_model_dependencies_available()

    with st.sidebar:
        st.header("分析设置")
        mode_label = st.radio(
            "分析方式",
            [
                "演示案例",
                "规则解析",
                "本地模型（可选）",
                "近10年阅读题库",
            ],
            index=0,
            on_change=reset_analysis,
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
        st.caption("通用分析只显示所选等级；题库模式以题库内的考试等级为准。")

    article = ""
    analyze_clicked = False
    bank_analyze_clicked = False
    pending_result = None
    pending_bank_entries = []
    permission = False
    needs_refresh_notice = False
    active_level = level

    if mode_label == "近10年阅读题库":
        years = sorted(
            {int(entry["year"]) for entry in exam_bank},
            reverse=True,
        )
        selected_years = st.multiselect(
            "选择年份",
            years,
            default=years,
            on_change=reset_analysis,
        )
        exam_level_options = ["N4", "N3", "N2", "N1"]
        bank_level = st.selectbox(
            "考试等级",
            exam_level_options,
            index=exam_level_options.index(level) if level in exam_level_options else 1,
        )
        active_level = bank_level
        pending_bank_entries = filter_exam_bank(exam_bank, selected_years)
        total_questions = sum(
            len(entry.get("questions", []))
            for entry in pending_bank_entries
        )
        st.info(
            "题库为按近10年题型和难度编写的原创模拟题，不包含或复刻受版权保护的历年真题。"
        )
        st.caption(
            f"当前选择 {len(pending_bank_entries)} 篇文章、"
            f"{total_questions} 道阅读题。"
        )
        if pending_bank_entries:
            st.dataframe(
                [
                    {
                        "年份": entry["year"],
                        "文章": entry["title"],
                        "水平": entry["level"],
                        "主题": entry["topic"],
                    }
                    for entry in pending_bank_entries
                ],
                hide_index=True,
                width="stretch",
            )
        bank_analyze_clicked = st.button(
            "自动分析题库",
            type="primary",
            disabled=not pending_bank_entries,
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
        previous_bank = st.session_state.get("bank_analysis")
        previous_result = st.session_state.get("analysis")
        if previous_bank is not None:
            previous_level = getattr(previous_bank, "level", "")
        elif previous_result is not None:
            previous_level = getattr(previous_result, "estimated_level", "")
    has_previous_result = (
        st.session_state.get("analysis") is not None
        or st.session_state.get("bank_analysis") is not None
    )
    if has_previous_result and previous_level and previous_level != active_level:
        reset_analysis()
        needs_refresh_notice = True

    if refresh_requested:
        reset_analysis()
        if mode_label == "近10年阅读题库" and pending_bank_entries:
            bank_analyze_clicked = True
        elif mode_label == "演示案例":
            analyze_clicked = True
        elif mode_label == "规则解析" and permission:
            analyze_clicked = True
        elif mode_label == "本地模型（可选）" and permission and model_deps_ready:
            analyze_clicked = True
        else:
            needs_refresh_notice = True

    if bank_analyze_clicked:
        st.session_state["show_answers"] = False
        st.session_state["bank_show_answers"] = False
        try:
            with st.spinner("正在批量分析文章并汇总知识点……"):
                bank_result = analyze_exam_bank(
                    pending_bank_entries,
                    analyzer,
                    level=active_level,
                    focus=focus,
                )
            st.session_state["bank_analysis"] = bank_result
            st.session_state["last_analysis_level"] = active_level
            st.session_state.pop("analysis", None)
            st.session_state.pop("last_article", None)
        except Exception as exc:
            st.error(str(exc))

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
            st.session_state["analysis"] = result
            st.session_state["last_analysis_level"] = level
            st.session_state["last_article"] = article
            st.session_state.pop("bank_analysis", None)
        except Exception as exc:
            st.error(str(exc))
            st.info("可以切换到演示案例或规则解析继续体验。")

    result = migrate_result(st.session_state.get("analysis"))
    if result is not None:
        st.session_state["analysis"] = result
    last_article = st.session_state.get("last_article", article)
    bank_result = st.session_state.get("bank_analysis")
    if needs_refresh_notice and not analyze_clicked and not bank_analyze_clicked:
        st.info("预估水平或刷新条件已变化，请点击左侧【刷新】重新分析。")
    if bank_result:
        render_bank_analysis(bank_result)
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


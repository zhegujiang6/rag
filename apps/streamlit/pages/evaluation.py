"""RAGAS 评测仪表盘 — 评测、可视化、对比、反馈汇总."""
import json
import time

import streamlit as st
from ui import require_login
import pandas as pd

from smart_doc_search.data.database import (
    SessionLocal, KnowledgeBase, Document, ParentChunk, DocKbRelation,
    EvaluationRun, EvaluationResult, Feedback, Message,
)
from smart_doc_search.services.rag_engine import rag_engine
from smart_doc_search.services.ragas_evaluator import ragas_evaluator, test_dataset_generator
from smart_doc_search.services.feedback_service import feedback_service
from smart_doc_search.core.config import settings

# Auth guard
require_login()

def get_user_id():
    """获取当前登录用户 ID"""
    return st.session_state.get("user_id", 1)


def get_db():
    """获取 SQLAlchemy 数据库会话（确保连接正确关闭）"""
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()


# ── 辅助函数：显示指标图表 ──────────────────────────────────────────

def _display_metrics_chart(all_metrics):
    """显示 RAGAS 指标柱状图和详细得分"""
    if not all_metrics:
        return

    # 计算各项指标的平均分
    avg = {
        "上下文精度": sum(m.context_precision for m in all_metrics) / len(all_metrics),
        "上下文召回": sum(m.context_recall for m in all_metrics) / len(all_metrics),
        "忠实度": sum(m.faithfulness for m in all_metrics) / len(all_metrics),
        "答案相关性": sum(m.answer_relevancy for m in all_metrics) / len(all_metrics),
        "实体召回": sum(m.context_entity_recall for m in all_metrics) / len(all_metrics),
    }

    # 创建 DataFrame 用于绘制图表
    chart_df = pd.DataFrame(
        list(avg.items()), columns=["指标", "分数"]
    )

    # 绘制柱状图
    st.subheader("RAGAS 指标得分")
    st.bar_chart(chart_df.set_index("指标"), use_container_width=True)

    # 显示每个指标的详细得分和评级
    for name, score in avg.items():
        delta_color = "normal" if score >= 0.5 else "inverse"
        st.metric(
            name, f"{score:.3f}",
            delta=f"{'✅' if score >= 0.7 else '⚠️' if score >= 0.4 else '❌'}",
        )


# ── 页面 UI ───────────────────────────────────────────────────────
st.title("📊 RAGAS 评测仪表盘")

db = get_db()

# ── 标签页布局 ────────────────────────────────────────────────────
tab_run, tab_dashboard, tab_dataset, tab_feedback = st.tabs([
    "🚀 运行评测", "📈 指标仪表盘", "📝 测试数据集", "💬 用户反馈",
])

# ====================================================================
# Tab 1: 运行评测
# ====================================================================
with tab_run:
    st.subheader("运行 RAGAS 评测")

    # 获取知识库列表
    kbs = db.query(KnowledgeBase).filter(
        KnowledgeBase.user_id == get_user_id()
    ).all()

    if not kbs:
        st.warning("没有知识库，请先创建知识库并上传文档")
    else:
        kb_options = {kb.id: kb.name for kb in kbs}
        eval_kb_id = st.selectbox(
            "选择知识库",
            options=list(kb_options.keys()),
            format_func=lambda x: kb_options[x],
            key="eval_kb",
        )

        # 评测参数设置
        col1, col2 = st.columns(2)
        with col1:
            test_count = st.number_input(
                "测试用例数量", min_value=3, max_value=50, value=10, step=1,
                help="从文档中生成多少个问答对用于评测"
            )
        with col2:
            eval_top_k = st.slider(
                "检索 Top-K", min_value=1, max_value=20, value=5,
                help="评测时使用的检索数量"
            )

        # 显示当前检索配置状态
        st.divider()
        st.caption("当前检索配置:")
        config_cols = st.columns(4)
        with config_cols[0]:
            st.caption(f"混合检索: {'✅' if settings.HYBRID_SEARCH_ENABLED else '❌'}")
        with config_cols[1]:
            st.caption(f"重排序: {'✅' if settings.RERANK_ENABLED else '❌'}")
        with config_cols[2]:
            st.caption(f"查询改写: {'✅' if settings.QUERY_REWRITE_ENABLED else '❌'}")
        with config_cols[3]:
            st.caption(f"上下文压缩: {'✅' if settings.CONTEXT_COMPRESSION_ENABLED else '❌'}")

        # 快速评测模式切换
        quick_mode = st.checkbox(
            "⚡ 快速评测",
            value=True,
            help="仅计算 Context Precision + Answer Relevancy（~5x 更快）。"
                 "关闭则计算全部 5 项 RAGAS 指标。"
        )

        # ── 测试数据来源 ──
        dataset_mode = st.radio(
            "测试数据来源",
            ["🤖 自动生成新题目", "📂 加载已保存的测试集"],
            horizontal=True,
            help="选「加载已保存」可确保两次评测使用相同题目，结果可对比"
        )

        loaded_qa_pairs = None
        if dataset_mode.startswith("📂"):
            saved = test_dataset_generator.list_datasets(kb_id=eval_kb_id)
            if saved:
                ds_options = {
                    s["path"]: f"{s['name']} ({s['pair_count']}题, {s['created_at']})"
                    for s in saved
                }
                selected_ds = st.selectbox(
                    "选择已保存的测试集",
                    options=list(ds_options.keys()),
                    format_func=lambda x: ds_options[x],
                )
                if selected_ds and st.button("📥 加载测试集", use_container_width=True):
                    try:
                        loaded_qa_pairs = test_dataset_generator.load_dataset(selected_ds)
                        st.success(f"已加载 {len(loaded_qa_pairs)} 个测试用例")
                        st.session_state.loaded_qa_pairs = loaded_qa_pairs
                    except Exception as e:
                        st.error(f"加载失败: {e}")
            else:
                st.info(f"知识库 #{eval_kb_id} 暂无已保存的测试集，请先自动生成并保存")

        # 如有已加载的测试集，显示预览
        if st.session_state.get("loaded_qa_pairs"):
            lp = st.session_state.loaded_qa_pairs
            st.caption(f"当前已加载测试集: {len(lp)} 题")
            with st.expander("预览题目"):
                for i, qa in enumerate(lp[:5]):
                    st.caption(f"Q{i+1}: {qa.get('question', '')[:80]}...")

        # 开始评测按钮
        if st.button("▶️ 开始评测", use_container_width=True, type="primary"):
            t_start = time.time()
            with st.status("正在评测...", expanded=True) as status:
                # ── 步骤1: 加载知识库文档分块 ──
                st.write("📄 加载知识库文档...")
                # 从两条关联路径收集文档ID
                kb_doc_ids = set()
                # 路径1: 直接通过 Document.knowledge_base_id 关联
                direct_docs = db.query(Document.id).filter(
                    Document.knowledge_base_id == eval_kb_id
                ).all()
                kb_doc_ids.update(d[0] for d in direct_docs)
                # 路径2: 通过 DocKbRelation 多对多关联
                rel_docs = db.query(DocKbRelation.document_id).filter(
                    DocKbRelation.knowledge_base_id == eval_kb_id
                ).all()
                kb_doc_ids.update(d[0] for d in rel_docs)

                if not kb_doc_ids:
                    st.error("知识库中没有关联的文档")
                    st.stop()

                # 获取所有父块
                parent_chunks = db.query(ParentChunk).filter(
                    ParentChunk.document_id.in_(list(kb_doc_ids))
                ).all()

                if not parent_chunks:
                    st.error("知识库中没有文档分块")
                    st.stop()

                # 准备分块数据
                chunks_data = [
                    {
                        "content": pc.content,
                        "document_id": pc.document_id,
                        "chunk_index": pc.chunk_index,
                    }
                    for pc in parent_chunks
                ]

                # ── 步骤2: 获取测试问答对 ──
                loaded = st.session_state.get("loaded_qa_pairs")
                if loaded:
                    qa_pairs = loaded
                    t1 = t2 = time.time()
                    st.write(f"📂 使用已加载的测试集: {len(qa_pairs)} 题")
                else:
                    t1 = time.time()
                    st.write("🤖 生成测试问答对...")
                    actual_count = min(test_count, len(parent_chunks) * 2)
                    qa_pairs = test_dataset_generator.generate_from_chunks(
                        chunks_data, max_pairs=actual_count
                    )
                    t2 = time.time()
                    st.write(f"✅ 生成了 {len(qa_pairs)} 个测试问答对 ({(t2-t1):.1f}s)")

                    # Offer to save the generated dataset for future re-use
                    st.session_state.last_generated_qa = qa_pairs
                    st.session_state.last_gen_kb = eval_kb_id

                if not qa_pairs:
                    st.error("没有可用的测试数据")
                    st.stop()

                # ── 步骤3: 创建评测记录 ──
                eval_run = EvaluationRun(
                    knowledge_base_id=eval_kb_id,
                    config_snapshot={
                        "hybrid_search": settings.HYBRID_SEARCH_ENABLED,
                        "rerank": settings.RERANK_ENABLED,
                        "query_rewrite": settings.QUERY_REWRITE_ENABLED,
                        "context_compression": settings.CONTEXT_COMPRESSION_ENABLED,
                        "top_k": eval_top_k,
                        "threshold": settings.SIMILARITY_THRESHOLD,
                        "quick_mode": quick_mode,
                    },
                    test_case_count=len(qa_pairs),
                )
                db.add(eval_run)
                db.commit()
                run_id = eval_run.id

                # ── 步骤4: 对每个问答对进行评测 ──
                metric_name = "快速评测 (2项)" if quick_mode else "完整评测 (5项)"
                st.write(f"📊 计算 RAGAS 指标 — {metric_name}...")
                status_text = st.empty()
                progress_bar = st.progress(0.0)
                all_metrics = []
                t_gen_total = 0.0
                t_ragas_total = 0.0

                for i, qa in enumerate(qa_pairs):
                    question = qa.get("question", "")
                    ground_truth = qa.get("answer", "")

                    if not question:
                        continue

                    status_text.write(
                        f"正在评测 {i+1}/{len(qa_pairs)}: "
                        f"{question[:50]}..."
                    )

                    # 生成回答 + 捕获上下文（一次管线，不重复调用）
                    t_g0 = time.time()
                    answer_parts = []
                    contexts = []
                    stream = rag_engine.generate_rag_stream(
                        question, eval_kb_id, db, top_k=eval_top_k
                    )
                    for event in stream:
                        if event["type"] == "token":
                            answer_parts.append(event["content"])
                        elif event["type"] == "contexts":
                            contexts = event.get("data", [])
                        elif event["type"] == "error":
                            answer_parts.append(event["content"])
                            break
                    answer = "".join(answer_parts)
                    t_g1 = time.time()
                    t_gen_total += (t_g1 - t_g0)

                    # 计算 RAGAS 指标
                    t_r0 = time.time()
                    if quick_mode:
                        metrics = ragas_evaluator.evaluate_quick(
                            question=question,
                            answer=answer,
                            contexts=contexts,
                        )
                    else:
                        metrics = ragas_evaluator.evaluate(
                            question=question,
                            answer=answer,
                            contexts=contexts,
                            ground_truth=ground_truth,
                        )
                    t_r1 = time.time()
                    t_ragas_total += (t_r1 - t_r0)
                    all_metrics.append(metrics)

                    # 保存评测结果
                    result = EvaluationResult(
                        run_id=run_id,
                        question=question,
                        ground_truth_answer=ground_truth,
                        generated_answer=answer,
                        retrieved_context="\n---\n".join(contexts),
                        **metrics.to_dict(),
                    )
                    db.add(result)
                    db.commit()

                    progress_bar.progress((i + 1) / len(qa_pairs))
                    status_text.write(
                        f"评测 {i+1}/{len(qa_pairs)} ✅ | "
                        f"生成 {(t_g1-t_g0):.1f}s | RAGAS {(t_r1-t_r0):.1f}s"
                    )

                # ── 步骤5: 计算平均分并更新评测记录 ──
                if all_metrics:
                    m = all_metrics[0].__class__(
                        context_precision=sum(m.context_precision for m in all_metrics) / len(all_metrics),
                        context_recall=sum(m.context_recall for m in all_metrics) / len(all_metrics),
                        faithfulness=sum(m.faithfulness for m in all_metrics) / len(all_metrics),
                        answer_relevancy=sum(m.answer_relevancy for m in all_metrics) / len(all_metrics),
                        context_entity_recall=sum(m.context_entity_recall for m in all_metrics) / len(all_metrics),
                    )

                    eval_run.avg_context_precision = m.context_precision
                    eval_run.avg_context_recall = m.context_recall
                    eval_run.avg_faithfulness = m.faithfulness
                    eval_run.avg_answer_relevancy = m.answer_relevancy
                    eval_run.avg_context_entity_recall = m.context_entity_recall
                    db.commit()

                # 更新状态并显示结果
                t_total = time.time() - t_start
                status.update(
                    label=f"✅ 评测完成! 总耗时 {t_total:.0f}s "
                          f"(生成 {t_gen_total:.0f}s / RAGAS {t_ragas_total:.0f}s)",
                    state="complete",
                )

                # 显示评测结果
                st.success(
                    f"评测完成! 运行 ID: {run_id} | "
                    f"模式: {'⚡快速' if quick_mode else '🔬完整'} | "
                    f"耗时: {t_total:.0f}s "
                    f"(生成: {t_gen_total:.0f}s / RAGAS: {t_ragas_total:.0f}s)"
                )
                if all_metrics:
                    _display_metrics_chart(all_metrics)

                # ── Offer to save the test set for reproducible comparison ──
                st.divider()
                st.caption("💾 保存本次测试集，供后续 A/B 对比使用（确保题目一致）")
                save_label = st.text_input(
                    "标签（可选，如 baseline / optimized）",
                    placeholder="baseline",
                    key="save_label",
                )
                if st.button("💾 保存测试集", key="save_btn"):
                    path = test_dataset_generator.save_dataset(
                        qa_pairs, eval_kb_id, label=save_label.strip()
                    )
                    st.success(f"已保存到: {path}")

# ====================================================================
# Tab 2: 指标仪表盘
# ====================================================================
with tab_dashboard:
    st.subheader("历史评测结果")

    # 获取最近20次评测记录
    runs = db.query(EvaluationRun).order_by(
        EvaluationRun.created_at.desc()
    ).limit(20).all()

    if not runs:
        st.info("还没有运行过评测。在「运行评测」标签页中运行一次。")
    else:
        # 构建评测结果汇总表格数据
        run_data = []
        for r in runs:
            kb_name = kb_options.get(r.knowledge_base_id, f"KB#{r.knowledge_base_id}") if 'kb_options' in dir() else f"KB#{r.knowledge_base_id}"
            run_data.append({
                "ID": r.id,
                "知识库": kb_name,
                "用例数": r.test_case_count,
                "上下文精度": f"{r.avg_context_precision:.3f}",
                "上下文召回": f"{r.avg_context_recall:.3f}",
                "忠实度": f"{r.avg_faithfulness:.3f}",
                "答案相关性": f"{r.avg_answer_relevancy:.3f}",
                "实体召回": f"{r.avg_context_entity_recall:.3f}",
                "综合": f"{(r.avg_context_precision + r.avg_context_recall + r.avg_faithfulness + r.avg_answer_relevancy + r.avg_context_entity_recall) / 5:.3f}",
                "时间": r.created_at.strftime("%m-%d %H:%M") if r.created_at else "",
            })

        # 显示汇总表格
        df = pd.DataFrame(run_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # 选择特定评测记录查看详细结果
        if runs:
            selected_run_id = st.selectbox(
                "查看详细结果",
                options=[r.id for r in runs],
                format_func=lambda x: f"Run #{x}",
                key="detail_run",
            )

            # 获取该评测的所有详细结果
            selected_results = db.query(EvaluationResult).filter(
                EvaluationResult.run_id == selected_run_id
            ).all()

            if selected_results:
                st.subheader("详细结果")
                for res in selected_results:
                    with st.expander(f"Q: {res.question[:80]}...", expanded=False):
                        st.markdown(f"**问题:** {res.question}")
                        st.markdown(f"**标准答案:** {res.ground_truth_answer}")
                        st.markdown(f"**生成答案:** {res.generated_answer}")
                        # 显示各项指标得分
                        col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
                        col_m1.metric("上下文精度", f"{res.context_precision:.3f}")
                        col_m2.metric("上下文召回", f"{res.context_recall:.3f}")
                        col_m3.metric("忠实度", f"{res.faithfulness:.3f}")
                        col_m4.metric("答案相关性", f"{res.answer_relevancy:.3f}")
                        col_m5.metric("实体召回", f"{res.context_entity_recall:.3f}")

# ====================================================================
# Tab 3: 测试数据集管理
# ====================================================================
with tab_dataset:
    st.subheader("测试数据集管理")

    if 'kbs' not in dir() or not kbs:
        st.warning("请先创建知识库")
    else:
        # ── Saved datasets ──
        all_datasets = test_dataset_generator.list_datasets()
        if all_datasets:
            st.caption(f"📁 共 {len(all_datasets)} 个已保存的测试集")
            for ds in all_datasets:
                col_a, col_b = st.columns([4, 1])
                with col_a:
                    st.markdown(
                        f"📄 **{ds['name']}** — {ds['pair_count']} 题 "
                        f"— {ds['created_at']}"
                    )
                with col_b:
                    if st.button("📥 加载", key=f"load_{ds['name']}"):
                        st.session_state.loaded_qa_pairs = (
                            test_dataset_generator.load_dataset(ds['path'])
                        )
                        st.success(f"已加载 {ds['pair_count']} 题，前往「运行评测」使用")
                        st.rerun()
            st.divider()
        else:
            st.info("暂无已保存的测试集。生成并保存后出现在这里，可重复加载用于 A/B 对比评测。")

        # ── Manual generation ──
        st.subheader("手动生成新测试集")
        ds_kb_id = st.selectbox(
            "知识库",
            options=list(kb_options.keys()),
            format_func=lambda x: kb_options[x],
            key="ds_kb",
        )

        col_gen1, col_gen2 = st.columns([1, 1])
        with col_gen1:
            gen_count = st.number_input(
                "生成数量", min_value=5, max_value=100, value=15, step=5,
                key="gen_count"
            )
        with col_gen2:
            st.caption("")
            st.caption("")
            if st.button("🤖 自动生成测试集", use_container_width=True):
                with st.spinner("正在生成..."):
                    kb_doc_ids = set()
                    direct_docs = db.query(Document.id).filter(
                        Document.knowledge_base_id == ds_kb_id
                    ).all()
                    kb_doc_ids.update(d[0] for d in direct_docs)
                    rel_docs = db.query(DocKbRelation.document_id).filter(
                        DocKbRelation.knowledge_base_id == ds_kb_id
                    ).all()
                    kb_doc_ids.update(d[0] for d in rel_docs)

                    if kb_doc_ids:
                        parent_chunks = db.query(ParentChunk).filter(
                            ParentChunk.document_id.in_(list(kb_doc_ids))
                        ).all()

                    if parent_chunks:
                        chunks_data = [
                            {
                                "content": pc.content,
                                "document_id": pc.document_id,
                                "chunk_index": pc.chunk_index,
                                "filename": "",
                            }
                            for pc in parent_chunks
                        ]
                        qa_pairs = test_dataset_generator.generate_from_chunks(
                            chunks_data, max_pairs=gen_count
                        )
                        st.session_state.generated_qa = qa_pairs
                        st.success(f"生成了 {len(qa_pairs)} 个问答对")

        # Display generated QA pairs
        if "generated_qa" in st.session_state and st.session_state.generated_qa:
            st.divider()
            st.subheader(f"生成的测试用例 ({len(st.session_state.generated_qa)} 个)")

            for i, qa in enumerate(st.session_state.generated_qa):
                with st.expander(f"Q{i+1}: {qa.get('question', '')[:60]}...", expanded=False):
                    st.markdown(f"**问题:** {qa.get('question', '')}")
                    st.markdown(f"**答案:** {qa.get('answer', '')}")
                    st.caption(f"来源: {qa.get('source_filename', '')} "
                              f"(片段 {qa.get('source_chunk_index', '')})")

            col_save, col_export = st.columns(2)
            with col_save:
                save_label = st.text_input("标签", placeholder="baseline", key="gen_save_label")
                if st.button("💾 保存此测试集", key="gen_save", use_container_width=True):
                    path = test_dataset_generator.save_dataset(
                        st.session_state.generated_qa, ds_kb_id, label=save_label.strip()
                    )
                    st.success(f"已保存: {path}")
            with col_export:
                st.caption("")
                if st.button("📥 导出为 JSON", use_container_width=True):
                    st.download_button(
                        label="下载 JSON",
                        data=json.dumps(
                            st.session_state.generated_qa, ensure_ascii=False, indent=2
                        ),
                        file_name=f"test_dataset_kb{ds_kb_id}.json",
                        mime="application/json",
                    )

# ====================================================================
# Tab 4: 用户反馈汇总
# ====================================================================
with tab_feedback:
    st.subheader("用户反馈汇总")

    # 选择知识库（可选，0表示全部）
    fb_kb_id = st.selectbox(
        "知识库（可选）",
        options=[0] + list(kb_options.keys()) if 'kb_options' in dir() else [0],
        format_func=lambda x: kb_options.get(x, "全部") if 'kb_options' in dir() else "全部",
        key="fb_kb",
    )

    # 设置时间范围
    fb_days = st.slider("时间范围（天）", 7, 90, 30, key="fb_days")

    # 获取反馈统计数据
    stats = feedback_service.get_stats(
        knowledge_base_id=fb_kb_id if fb_kb_id > 0 else None,
        db=db,
        days=fb_days,
    )

    # 显示统计指标
    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    col_s1.metric("总反馈数", stats["total"])
    col_s2.metric("好评率", f"{stats['positive_rate']:.1%}")
    col_s3.metric("平均评分", f"{stats['avg_rating']:.2f}")
    col_s4.metric("差评数", stats["negative"])

    # 显示评价分类统计
    col_p, col_n, col_z = st.columns(3)
    col_p.metric("👍 好评", stats["positive"])
    col_n.metric("👎 差评", stats["negative"])
    col_z.metric("➖ 中性", stats["neutral"])

    # 显示反馈类型分布
    if stats["by_type"]:
        st.divider()
        st.caption("反馈类型分布:")
        type_df = pd.DataFrame(
            list(stats["by_type"].items()),
            columns=["类型", "数量"]
        )
        st.dataframe(type_df, use_container_width=True, hide_index=True)

# 关闭数据库连接
db.close()

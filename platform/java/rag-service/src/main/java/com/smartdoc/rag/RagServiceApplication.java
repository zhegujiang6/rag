package com.smartdoc.rag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cloud.client.discovery.EnableDiscoveryClient;

/**
 * RAG 检索与对话服务入口。
 *
 * <p>职责：
 * <ul>
 *   <li>语义检索 — 向量化查询 → ChromaDB 搜索</li>
 *   <li>混合检索 — BM25 关键词 + 语义向量 → RRF 融合</li>
 *   <li>查询改写 — 多查询变体扩展 + HyDE</li>
 *   <li>重排序 — LLM/Cross-Attention 重排</li>
 *   <li>上下文压缩 — 句子级相关性过滤</li>
 *   <li>RAG 问答 — 流式 SSE 生成</li>
 *   <li>普通对话 — 流式 SSE 生成</li>
 *   <li>检索结果缓存 — Redis 热点查询缓存</li>
 * </ul>
 *
 * <p>增强管线：
 * <pre>
 *   query → [rewrite] → [hybrid search] → [rerank] → parent expansion
 *         → [context compression] → LLM generation (SSE)
 * </pre>
 *
 * <p>API 端点：
 * <pre>
 *   POST /api/v1/search/semantic     — 语义检索
 *   POST /api/v1/search/hybrid       — 混合检索
 *   POST /api/v1/chat/rag/stream     — RAG 问答 (SSE)
 *   POST /api/v1/chat/stream         — 普通对话 (SSE)
 *   GET  /api/v1/conversations       — 对话列表
 *   GET  /api/v1/conversations/{id}  — 对话消息
 *   POST /api/v1/feedback            — 提交反馈
 * </pre>
 */
@SpringBootApplication(scanBasePackages = {"com.smartdoc.rag", "com.smartdoc.common"})
@EnableDiscoveryClient
@EnableCaching
public class RagServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(RagServiceApplication.class, args);
    }
}

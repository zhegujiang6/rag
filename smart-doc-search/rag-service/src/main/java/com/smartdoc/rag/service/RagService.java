package com.smartdoc.rag.service;

import com.smartdoc.rag.dto.RagChatRequest;
import com.smartdoc.rag.dto.SearchResult;
import reactor.core.publisher.Flux;

import java.util.List;
import java.util.Map;

/**
 * RAG 引擎服务 — 核心检索+生成管线。
 *
 * <p>增强管线（按配置开关控制）：
 * <pre>
 *   query → [rewrite] → [hybrid search] → [rerank] → parent expansion
 *         → [context compression] → LLM generation (SSE)
 * </pre>
 */
public interface RagService {

    /**
     * 增强检索 (完整管线)。
     *
     * @param query            用户查询
     * @param knowledgeBaseId  知识库 ID
     * @param topK             返回结果数
     * @return 检索结果 + 调试信息
     */
    Map<String, Object> retrieveEnhanced(String query, Long knowledgeBaseId, int topK);

    /**
     * RAG 流式生成回答。
     *
     * @param request 请求参数 (query, kbId, conversationHistory)
     * @return SSE 流式事件 (status/token/sources/retrieval_details/error)
     */
    Flux<String> generateRagStream(RagChatRequest request);

    /**
     * 普通对话流式生成 (不基于文档)。
     *
     * @param query               用户输入
     * @param conversationHistory 历史对话
     * @return SSE 流式 token
     */
    Flux<String> generateChatStream(String query, List<Map<String, String>> conversationHistory);
}

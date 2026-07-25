package com.smartdoc.evaluation.client;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

import java.util.Map;

/**
 * RAG Service Feign 客户端。
 *
 * <p>评测服务通过 Feign 调用 rag-service 获取检索结果，
 * 避免直接操作 ChromaDB，保持服务边界清晰。
 */
@FeignClient(name = "rag-service")
public interface RagServiceClient {

    /**
     * 调用 rag-service 的语义检索接口。
     */
    @PostMapping("/api/v1/search/semantic")
    Map<String, Object> semanticSearch(@RequestBody Map<String, Object> request);

    /**
     * 调用 rag-service 的混合检索接口。
     */
    @PostMapping("/api/v1/search/hybrid")
    Map<String, Object> hybridSearch(@RequestBody Map<String, Object> request);
}

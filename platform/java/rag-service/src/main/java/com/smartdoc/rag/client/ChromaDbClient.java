package com.smartdoc.rag.client;

import com.smartdoc.rag.dto.ChromaSearchRequest;
import com.smartdoc.rag.dto.ChromaSearchResponse;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;
import reactor.core.publisher.Mono;

/**
 * ChromaDB Python Sidecar HTTP 客户端。
 *
 * <p>通过 WebFlux {@code @HttpExchange} 声明式调用。
 * Sidecar 是一个 FastAPI 服务，封装了 ChromaDB 的原生 Python SDK。
 */
@HttpExchange("/api/v1")
public interface ChromaDbClient {

    /**
     * 向量相似度搜索。
     */
    @PostExchange("/collections/{collectionName}/search")
    Mono<ChromaSearchResponse> search(
            @RequestBody ChromaSearchRequest request);

    /**
     * 批量写入向量。
     */
    @PostExchange("/collections/{collectionName}/add")
    Mono<Void> addEmbeddings(
            @RequestBody Object embeddings);
}

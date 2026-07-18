package com.smartdoc.rag.service.impl;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartdoc.common.context.UserContext;
import com.smartdoc.common.exception.BusinessException;
import com.smartdoc.common.exception.ErrorCode;
import com.smartdoc.rag.dto.SearchRequest;
import com.smartdoc.rag.dto.SearchResult;
import com.smartdoc.rag.service.SearchService;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import io.github.resilience4j.ratelimiter.annotation.RateLimiter;
import io.github.resilience4j.retry.annotation.Retry;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@Service
@RequiredArgsConstructor
public class SearchServiceImpl implements SearchService {
    private final ObjectMapper objectMapper;
    @Value("${embedding.api-base:https://api.openai.com/v1}") private String embeddingBase;
    @Value("${embedding.api-key:}") private String embeddingKey;
    @Value("${embedding.model:text-embedding-3-small}") private String embeddingModel;
    @Value("${chromadb.base-url:http://127.0.0.1:8001}") private String chromaBase;
    @Override
    @CircuitBreaker(name = "embeddingApi", fallbackMethod = "searchFallback")
    @Retry(name = "embeddingApi")
    @RateLimiter(name = "embeddingApi")
    public List<SearchResult> semanticSearch(SearchRequest request) { return search(request); }

    @Override
    @CircuitBreaker(name = "embeddingApi", fallbackMethod = "searchFallback")
    @Retry(name = "embeddingApi")
    @RateLimiter(name = "embeddingApi")
    public List<SearchResult> hybridSearch(SearchRequest request) { return search(request); }

    /** 上游 Embedding/向量库不可用时快速降级，避免占满 Tomcat 工作线程。 */
    private List<SearchResult> searchFallback(SearchRequest request, Throwable error) {
        return List.of();
    }
    private List<SearchResult> search(SearchRequest request) {
        if (request.getQuery() == null || request.getQuery().isBlank() || request.getKnowledgeBaseId() == null || UserContext.getUserId() == null) throw new BusinessException(ErrorCode.PARAM_INVALID);
        if (embeddingKey.isBlank()) throw new BusinessException(ErrorCode.EMBEDDING_FAILED);
        JsonNode embedding = RestClient.create(embeddingBase).post().uri("/embeddings").contentType(MediaType.APPLICATION_JSON).header("Authorization", "Bearer " + embeddingKey).body(Map.of("model", embeddingModel, "input", request.getQuery())).retrieve().body(JsonNode.class);
        List<Double> vector = new ArrayList<>(); embedding.path("data").get(0).path("embedding").forEach(n -> vector.add(n.asDouble()));
        JsonNode rows = RestClient.create(chromaBase).post().uri("/api/v1/collections/kb-" + request.getKnowledgeBaseId() + "/search").contentType(MediaType.APPLICATION_JSON).body(Map.of("query_embedding", vector, "top_k", request.getTopK() == null ? 5 : request.getTopK(), "similarity_threshold", request.getSimilarityThreshold() == null ? .35 : request.getSimilarityThreshold(), "where_filter", Map.of("user_id", UserContext.getUserId()))).retrieve().body(JsonNode.class);
        List<SearchResult> results = new ArrayList<>();
        for (JsonNode row : rows) results.add(SearchResult.builder().chromaId(row.path("chroma_id").asText()).documentId(row.path("document_id").asLong()).parentChunkId(row.path("parent_chunk_id").asLong()).chunkIndex(row.path("chunk_index").asInt()).content(row.path("content").asText()).score(row.path("score").asDouble()).metadata(objectMapper.convertValue(row.path("metadata"), Map.class)).build());
        return results;
    }
}

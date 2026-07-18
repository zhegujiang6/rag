package com.smartdoc.rag.service;

import com.smartdoc.rag.dto.SearchRequest;
import com.smartdoc.rag.dto.SearchResult;

import java.util.List;

/**
 * 检索服务接口 — 语义检索 & 混合检索。
 */
public interface SearchService {

    /**
     * 语义检索 (纯向量相似度, 无额外增强)。
     */
    List<SearchResult> semanticSearch(SearchRequest request);

    /**
     * 混合检索 (BM25 + 语义向量 → RRF 融合)。
     */
    List<SearchResult> hybridSearch(SearchRequest request);
}

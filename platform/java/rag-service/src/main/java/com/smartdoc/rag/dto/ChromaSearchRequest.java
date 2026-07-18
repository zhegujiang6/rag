package com.smartdoc.rag.dto;

import lombok.Data;
import java.util.List;
import java.util.Map;

/**
 * ChromaDB 检索请求。
 */
@Data
public class ChromaSearchRequest {

    private List<Double> queryEmbedding;
    private int topK;
    private double similarityThreshold;
    private Map<String, Object> whereFilter;
}

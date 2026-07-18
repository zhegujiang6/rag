package com.smartdoc.rag.dto;

import lombok.Data;

/**
 * 检索请求 DTO。
 */
@Data
public class SearchRequest {

    private String query;
    private Long knowledgeBaseId;
    private Integer topK;
    private Double similarityThreshold;
}

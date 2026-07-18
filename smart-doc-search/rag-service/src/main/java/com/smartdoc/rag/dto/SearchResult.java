package com.smartdoc.rag.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.Map;

/**
 * 检索结果 DTO。
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class SearchResult {

    private String chromaId;
    private Long documentId;
    private Long parentChunkId;
    private Integer chunkIndex;
    private String content;
    private Double score;
    private Double rerankScore;
    private Map<String, Object> metadata;
}

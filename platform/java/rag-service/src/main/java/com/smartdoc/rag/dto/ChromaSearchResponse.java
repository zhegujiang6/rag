package com.smartdoc.rag.dto;

import lombok.Data;
import java.util.List;

/**
 * ChromaDB 检索响应。
 */
@Data
public class ChromaSearchResponse {

    private List<SearchResult> results;
    private int total;
}

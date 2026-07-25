package com.smartdoc.rag.dto;

import lombok.Data;

import java.util.List;
import java.util.Map;

/**
 * RAG 对话请求 DTO。
 */
@Data
public class RagChatRequest {

    private String query;
    private Long knowledgeBaseId;
    private Integer topK;
    private List<Map<String, String>> conversationHistory;
}

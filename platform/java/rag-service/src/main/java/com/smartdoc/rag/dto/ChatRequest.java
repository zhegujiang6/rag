package com.smartdoc.rag.dto;

import lombok.Data;
import java.util.List;
import java.util.Map;

/**
 * 普通对话请求。
 */
@Data
public class ChatRequest {

    private String query;
    private List<Map<String, String>> conversationHistory;
}

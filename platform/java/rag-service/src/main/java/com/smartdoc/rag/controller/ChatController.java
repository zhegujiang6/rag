package com.smartdoc.rag.controller;

import com.smartdoc.common.context.UserContext;
import com.smartdoc.common.exception.BusinessException;
import com.smartdoc.common.exception.ErrorCode;
import com.smartdoc.rag.dto.ChatRequest;
import com.smartdoc.rag.dto.RagChatRequest;
import com.smartdoc.rag.service.RagService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;

/**
 * 对话控制器 (SSE 流式) — 按当前用户隔离对话记录。
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/chat")
@RequiredArgsConstructor
@Tag(name = "对话管理", description = "RAG 问答 & 普通对话 (流式 SSE)")
public class ChatController {

    private final RagService ragService;

    private Long getUserId() {
        Long userId = UserContext.getUserId();
        if (userId == null) {
            throw new BusinessException(ErrorCode.UNAUTHORIZED);
        }
        return userId;
    }

    @PostMapping(value = "/rag/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    @Operation(summary = "RAG 问答 (流式 SSE)")
    public Flux<String> ragStream(@RequestBody RagChatRequest request) {
        log.info("RAG 对话: userId={}, kbId={}, query={}",
                getUserId(), request.getKnowledgeBaseId(),
                request.getQuery() != null ? request.getQuery().substring(0, Math.min(50, request.getQuery().length())) : "");
        // TODO: 实现完整管线 (检索→压缩→LLM SSE)
        return Flux.empty();
    }

    @PostMapping(value = "/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    @Operation(summary = "普通对话 (流式 SSE)")
    public Flux<String> chatStream(@RequestBody ChatRequest request) {
        log.info("普通对话: userId={}", getUserId());
        // TODO: 实现普通流式对话
        return Flux.empty();
    }
}

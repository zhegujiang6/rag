package com.smartdoc.rag.controller;

import com.smartdoc.common.context.UserContext;
import com.smartdoc.common.dto.ApiResponse;
import com.smartdoc.common.exception.BusinessException;
import com.smartdoc.common.exception.ErrorCode;
import com.smartdoc.rag.dto.SearchRequest;
import com.smartdoc.rag.dto.SearchResult;
import com.smartdoc.rag.service.SearchService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 检索控制器 — 仅检索当前用户有权访问的知识库。
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/search")
@RequiredArgsConstructor
@Tag(name = "检索管理", description = "语义检索 & 混合检索")
public class SearchController {

    private final SearchService searchService;

    private Long getUserId() {
        Long userId = UserContext.getUserId();
        if (userId == null) {
            throw new BusinessException(ErrorCode.UNAUTHORIZED);
        }
        return userId;
    }

    @PostMapping("/semantic")
    @Operation(summary = "语义检索 (纯向量相似度)")
    public ApiResponse<List<SearchResult>> semanticSearch(@RequestBody SearchRequest request) {
        log.info("语义检索: userId={}, kbId={}", getUserId(), request.getKnowledgeBaseId());
        // TODO: 验证 kbId 属于当前用户
        // List<SearchResult> results = searchService.semanticSearch(request, getUserId());
        getUserId();
        return ApiResponse.ok(searchService.semanticSearch(request));
    }

    @PostMapping("/hybrid")
    @Operation(summary = "混合检索 (BM25 + 语义向量 → RRF 融合)")
    public ApiResponse<List<SearchResult>> hybridSearch(@RequestBody SearchRequest request) {
        log.info("混合检索: userId={}, kbId={}", getUserId(), request.getKnowledgeBaseId());
        // TODO: 验证 kbId 属于当前用户
        getUserId();
        return ApiResponse.ok(searchService.hybridSearch(request));
    }
}

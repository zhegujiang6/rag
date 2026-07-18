package com.smartdoc.document.controller;

import com.smartdoc.common.context.UserContext;
import com.smartdoc.common.dto.ApiResponse;
import com.smartdoc.common.exception.BusinessException;
import com.smartdoc.common.exception.ErrorCode;
import com.smartdoc.document.dto.KbCreateRequest;
import com.smartdoc.document.dto.KbResponse;
import com.smartdoc.document.service.KnowledgeBaseService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 知识库管理控制器 — 按当前登录用户隔离。
 */
@RestController
@RequestMapping("/api/v1/knowledge-bases")
@RequiredArgsConstructor
@Tag(name = "知识库管理", description = "知识库 CRUD & 文档关联")
public class KnowledgeBaseController {

    private final KnowledgeBaseService kbService;

    private Long getUserId() {
        Long userId = UserContext.getUserId();
        if (userId == null) {
            throw new BusinessException(ErrorCode.UNAUTHORIZED);
        }
        return userId;
    }

    @PostMapping
    @Operation(summary = "创建知识库")
    public ApiResponse<KbResponse> create(@Valid @RequestBody KbCreateRequest request) {
        KbResponse resp = kbService.create(request, getUserId());
        return ApiResponse.ok(resp);
    }

    @GetMapping
    @Operation(summary = "知识库列表 — 仅返回当前用户的")
    public ApiResponse<List<KbResponse>> list() {
        List<KbResponse> list = kbService.listByUser(getUserId());
        return ApiResponse.ok(list);
    }

    @GetMapping("/{id}")
    @Operation(summary = "知识库详情")
    public ApiResponse<KbResponse> getById(@PathVariable Long id) {
        // TODO: 校验 kb.userId == getUserId()
        return ApiResponse.ok(kbService.get(id, getUserId()));
    }

    @DeleteMapping("/{id}")
    @Operation(summary = "删除知识库 — 仅能删除自己的")
    public ApiResponse<Void> delete(@PathVariable Long id) {
        kbService.delete(id, getUserId());
        return ApiResponse.ok(null);
    }

    @PostMapping("/{id}/documents/{docId}")
    @Operation(summary = "将文档添加到知识库")
    public ApiResponse<Void> addDocument(@PathVariable Long id, @PathVariable Long docId) {
        kbService.addDocument(id, docId, getUserId());
        return ApiResponse.ok(null);
    }

    @DeleteMapping("/{id}/documents/{docId}")
    @Operation(summary = "从知识库移除文档")
    public ApiResponse<Void> removeDocument(@PathVariable Long id, @PathVariable Long docId) {
        kbService.removeDocument(id, docId, getUserId());
        return ApiResponse.ok(null);
    }
}

package com.smartdoc.document.controller;

import com.smartdoc.common.context.UserContext;
import com.smartdoc.common.dto.ApiResponse;
import com.smartdoc.common.dto.PageResult;
import com.smartdoc.common.exception.BusinessException;
import com.smartdoc.common.exception.ErrorCode;
import com.smartdoc.document.dto.DocumentResponse;
import com.smartdoc.document.dto.DocumentUploadResponse;
import com.smartdoc.document.dto.ProcessStatusResponse;
import com.smartdoc.document.service.DocumentService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

/**
 * 文档管理控制器 — 所有操作按当前登录用户隔离。
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/documents")
@RequiredArgsConstructor
@Tag(name = "文档管理", description = "文档上传、查询、删除、标签")
public class DocumentController {

    private final DocumentService documentService;

    /** 获取当前用户 ID（Gateway 鉴权后通过 Header 传入） */
    private Long getUserId() {
        Long userId = UserContext.getUserId();
        if (userId == null) {
            throw new BusinessException(ErrorCode.UNAUTHORIZED);
        }
        return userId;
    }

    @PostMapping("/upload")
    @Operation(summary = "上传文档 (异步处理)")
    public ApiResponse<DocumentUploadResponse> upload(
            @RequestParam("file") MultipartFile file,
            @RequestParam(value = "kbId", required = false) Long kbId) {
        DocumentUploadResponse resp = documentService.upload(file, kbId, getUserId());
        return ApiResponse.ok(resp);
    }

    @PostMapping("/import-url")
    @Operation(summary = "网页导入")
    public ApiResponse<DocumentUploadResponse> importUrl(
            @RequestParam("url") String url,
            @RequestParam(value = "kbId", required = false) Long kbId) {
        DocumentUploadResponse resp = documentService.importUrl(url, kbId, getUserId());
        return ApiResponse.ok(resp);
    }

    @GetMapping
    @Operation(summary = "文档列表 — 仅返回当前用户文档")
    public ApiResponse<PageResult<DocumentResponse>> list(
            @RequestParam(required = false) Long kbId,
            @RequestParam(required = false) String[] tags,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int size) {
        // TODO: 实现按 userId + 筛选条件分页查询
        return ApiResponse.ok(documentService.list(kbId, page, size, getUserId()));
    }

    @GetMapping("/{id}")
    @Operation(summary = "文档详情")
    public ApiResponse<DocumentResponse> getById(@PathVariable Long id) {
        // TODO: 查询前校验 doc.userId == getUserId()
        return ApiResponse.ok(documentService.get(id, getUserId()));
    }

    @GetMapping("/{id}/status")
    @Operation(summary = "查询文档处理进度")
    public ApiResponse<ProcessStatusResponse> getStatus(@PathVariable Long id) {
        // TODO: 查询处理状态
        return ApiResponse.ok(documentService.getProcessStatus(id, getUserId()));
    }

    @DeleteMapping("/{id}")
    @Operation(summary = "删除文档 — 仅能删除自己的文档")
    public ApiResponse<Void> delete(@PathVariable Long id) {
        documentService.deleteDocument(id, getUserId());
        return ApiResponse.ok(null);
    }

    @PostMapping("/{id}/tags")
    @Operation(summary = "添加标签")
    public ApiResponse<Void> addTag(@PathVariable Long id, @RequestParam String tag) {
        documentService.addTag(id, tag, getUserId());
        return ApiResponse.ok(null);
    }

    @DeleteMapping("/{id}/tags/{tag}")
    @Operation(summary = "删除标签")
    public ApiResponse<Void> removeTag(@PathVariable Long id, @PathVariable String tag) {
        documentService.removeTag(id, tag, getUserId());
        return ApiResponse.ok(null);
    }
}

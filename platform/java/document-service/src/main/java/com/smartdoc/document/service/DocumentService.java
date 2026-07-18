package com.smartdoc.document.service;

import com.smartdoc.document.dto.DocumentUploadResponse;
import com.smartdoc.document.dto.ProcessStatusResponse;
import com.smartdoc.document.dto.DocumentResponse;
import com.smartdoc.common.dto.PageResult;
import org.springframework.web.multipart.MultipartFile;

/**
 * 文档管理服务 — 所有操作强制按 userId 隔离。
 */
public interface DocumentService {

    /** 上传文件并提交异步处理任务 */
    DocumentUploadResponse upload(MultipartFile file, Long kbId, Long userId);

    /** 网页导入 */
    DocumentUploadResponse importUrl(String url, Long kbId, Long userId);

    /** 查询处理进度 */
    ProcessStatusResponse getProcessStatus(Long documentId, Long userId);

    PageResult<DocumentResponse> list(Long kbId, int page, int size, Long userId);

    DocumentResponse get(Long documentId, Long userId);

    /** 删除文档 — 仅能删除自己的 */
    void deleteDocument(Long documentId, Long userId);

    /** 添加标签 */
    void addTag(Long documentId, String tag, Long userId);

    /** 移除标签 */
    void removeTag(Long documentId, String tag, Long userId);
}

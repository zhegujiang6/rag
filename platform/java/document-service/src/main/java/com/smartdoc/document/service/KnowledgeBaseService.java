package com.smartdoc.document.service;

import com.smartdoc.document.dto.KbCreateRequest;
import com.smartdoc.document.dto.KbResponse;

import java.util.List;

/**
 * 知识库管理服务 — 按 userId 隔离。
 */
public interface KnowledgeBaseService {

    /** 创建知识库 */
    KbResponse create(KbCreateRequest request, Long userId);

    /** 获取用户所有知识库 */
    List<KbResponse> listByUser(Long userId);

    KbResponse get(Long kbId, Long userId);

    /** 删除知识库 */
    void delete(Long kbId, Long userId);

    /** 添加文档到知识库 */
    void addDocument(Long kbId, Long docId, Long userId);

    /** 移除文档 */
    void removeDocument(Long kbId, Long docId, Long userId);
}

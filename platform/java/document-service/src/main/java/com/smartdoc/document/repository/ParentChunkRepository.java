package com.smartdoc.document.repository;

import com.smartdoc.document.model.ParentChunk;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

/**
 * 父块 Repository — 按 userId 隔离。
 */
@Repository
public interface ParentChunkRepository extends JpaRepository<ParentChunk, Long> {

    /** 按文档 ID 和 userId 查询父块 */
    List<ParentChunk> findByDocumentIdAndUserIdOrderByChunkIndex(Long documentId, Long userId);

    /** 按 ID 列表和 userId 查询（RAG 检索后获取父块内容） */
    List<ParentChunk> findByIdInAndUserId(List<Long> ids, Long userId);
}

package com.smartdoc.document.repository;

import com.smartdoc.document.model.SubChunk;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

/**
 * 子块 Repository — 按 userId 隔离。
 */
@Repository
public interface SubChunkRepository extends JpaRepository<SubChunk, Long> {

    /** 按文档 ID 和 userId 查询所有子块 */
    List<SubChunk> findByDocumentIdAndUserIdOrderByChunkIndex(Long documentId, Long userId);

    /** 按父块 ID 列表和 userId 查询 */
    List<SubChunk> findByParentChunkIdInAndUserId(List<Long> parentChunkIds, Long userId);
}

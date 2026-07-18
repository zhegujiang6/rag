package com.smartdoc.document.model;

import jakarta.persistence.*;
import lombok.*;

import java.time.Instant;

/**
 * 子块实体 (向量检索) — 冗余 user_id 用于权限校验。
 */
@Entity
@Table(name = "sub_chunks", indexes = {
        @Index(name = "idx_sc_parent", columnList = "parent_chunk_id"),
        @Index(name = "idx_sc_doc", columnList = "document_id"),
        @Index(name = "idx_sc_user", columnList = "user_id"),
        @Index(name = "idx_sc_chroma_id", columnList = "chroma_id"),
})
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class SubChunk {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "parent_chunk_id", nullable = false)
    private Long parentChunkId;

    @Column(name = "document_id", nullable = false)
    private Long documentId;

    @Column(name = "user_id", nullable = false)
    private Long userId;

    @Column(name = "chunk_index", nullable = false)
    private Integer chunkIndex;

    @Column(nullable = false, columnDefinition = "TEXT")
    private String content;

    @Column(name = "token_count")
    private Integer tokenCount;

    @Column(name = "chroma_id", length = 255)
    private String chromaId;

    @Column(name = "chunk_metadata", columnDefinition = "JSON")
    private String chunkMetadata;

    @Column(name = "created_at")
    private Instant createdAt;
}

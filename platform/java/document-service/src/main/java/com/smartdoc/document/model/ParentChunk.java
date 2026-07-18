package com.smartdoc.document.model;

import jakarta.persistence.*;
import lombok.*;

import java.time.Instant;

/**
 * 父块实体 (LLM 上下文) — 冗余 user_id 用于权限校验。
 */
@Entity
@Table(name = "parent_chunks", indexes = {
        @Index(name = "idx_pc_doc", columnList = "document_id"),
        @Index(name = "idx_pc_user", columnList = "user_id"),
})
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class ParentChunk {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

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

    @Column(name = "chunk_metadata", columnDefinition = "JSON")
    private String chunkMetadata;

    @Column(name = "created_at")
    private Instant createdAt;
}

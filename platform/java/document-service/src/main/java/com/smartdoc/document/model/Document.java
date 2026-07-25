package com.smartdoc.document.model;

import jakarta.persistence.*;
import lombok.*;

import java.time.Instant;

/**
 * 文档实体 — 上传文件/网页的元数据。
 */
@Entity
@Table(name = "documents", indexes = {
        @Index(name = "idx_doc_user", columnList = "user_id"),
        @Index(name = "idx_doc_kb", columnList = "knowledge_base_id"),
        @Index(name = "idx_doc_status", columnList = "status"),
})
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Document {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "user_id", nullable = false)
    private Long userId;

    @Column(name = "knowledge_base_id")
    private Long knowledgeBaseId;

    @Column(nullable = false, length = 500)
    private String filename;

    @Column(name = "original_filename", nullable = false, length = 500)
    private String originalFilename;

    @Column(name = "file_type", nullable = false, length = 20)
    private String fileType;

    @Column(name = "file_size")
    private Long fileSize;

    @Column(name = "file_path", length = 1000)
    private String filePath;

    @Column(name = "source_type", length = 10)
    private String sourceType;  // "file" | "web"

    @Column(name = "source_url", length = 2000)
    private String sourceUrl;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private DocStatus status;

    @Column(name = "error_message", columnDefinition = "TEXT")
    private String errorMessage;

    @Column(name = "chunk_count")
    private Integer chunkCount;

    @Column(columnDefinition = "JSON")
    private String tags;  // JSON 数组

    @Column(name = "created_at")
    private Instant createdAt;

    public enum DocStatus {
        uploading, parsing, chunking, embedding, completed, failed
    }
}

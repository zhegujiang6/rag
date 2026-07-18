package com.smartdoc.document.model;

import jakarta.persistence.*;
import lombok.*;

import java.time.Instant;

/**
 * 知识库实体。
 */
@Entity
@Table(name = "knowledge_bases", indexes = {
        @Index(name = "idx_kb_user", columnList = "user_id"),
})
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class KnowledgeBase {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "user_id", nullable = false)
    private Long userId;

    @Column(nullable = false, length = 200)
    private String name;

    @Column(columnDefinition = "TEXT")
    private String description;

    @Column(name = "is_default")
    private Boolean isDefault;

    @Column(name = "created_at")
    private Instant createdAt;

    @Column(name = "updated_at")
    private Instant updatedAt;
}

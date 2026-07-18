package com.smartdoc.rag.model;

import jakarta.persistence.*;
import lombok.*;

import java.time.Instant;

/**
 * 对话实体。
 */
@Entity
@Table(name = "conversations", indexes = {
        @Index(name = "idx_conv_user", columnList = "user_id"),
})
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Conversation {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "user_id", nullable = false)
    private Long userId;

    @Column(name = "knowledge_base_id")
    private Long knowledgeBaseId;

    @Column(length = 500)
    private String title;

    @Column(length = 10, nullable = false)
    private String mode;  // "rag" | "chat"

    @Column(name = "created_at")
    private Instant createdAt;

    @Column(name = "updated_at")
    private Instant updatedAt;
}

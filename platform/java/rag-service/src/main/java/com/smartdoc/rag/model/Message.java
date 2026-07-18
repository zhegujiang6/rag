package com.smartdoc.rag.model;

import jakarta.persistence.*;
import lombok.*;

import java.time.Instant;

/**
 * 消息实体 — 冗余 user_id 用于权限校验。
 */
@Entity
@Table(name = "messages", indexes = {
        @Index(name = "idx_msg_conv", columnList = "conversation_id"),
        @Index(name = "idx_msg_user", columnList = "user_id"),
})
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Message {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "conversation_id", nullable = false)
    private Long conversationId;

    @Column(name = "user_id", nullable = false)
    private Long userId;

    @Column(length = 10, nullable = false)
    private String role;  // "user" | "assistant" | "system"

    @Column(nullable = false, columnDefinition = "TEXT")
    private String content;

    @Column(columnDefinition = "JSON")
    private String sources;

    @Column(name = "retrieval_details", columnDefinition = "JSON")
    private String retrievalDetails;

    @Column(name = "token_count")
    private Integer tokenCount;

    @Column(name = "created_at")
    private Instant createdAt;
}

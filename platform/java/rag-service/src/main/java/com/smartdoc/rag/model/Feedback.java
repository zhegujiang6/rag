package com.smartdoc.rag.model;

import jakarta.persistence.*;
import lombok.*;

import java.time.Instant;

/**
 * 用户反馈实体。
 */
@Entity
@Table(name = "feedback", indexes = {
        @Index(name = "idx_fb_msg", columnList = "message_id"),
        @Index(name = "idx_fb_user", columnList = "user_id"),
})
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Feedback {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "message_id", nullable = false)
    private Long messageId;

    @Column(name = "user_id", nullable = false)
    private Long userId;

    @Column(columnDefinition = "INT DEFAULT 0")
    private Integer rating;  // -1=差评, 0=中性, 1=好评

    @Column(name = "feedback_type", length = 50)
    private String feedbackType;

    @Column(columnDefinition = "TEXT")
    private String comment;

    @Column(name = "created_at")
    private Instant createdAt;
}

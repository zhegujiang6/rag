package com.smartdoc.document.model;

import jakarta.persistence.*;
import lombok.*;

import java.time.Instant;

/**
 * 事务消息表。业务数据与待发送消息在同一 MySQL 事务中提交，
 * 由独立发布器在提交后投递 RocketMQ，避免双写不一致。
 */
@Entity
@Table(name = "outbox_events", indexes = {
        @Index(name = "idx_outbox_dispatch", columnList = "status,next_attempt_at"),
        @Index(name = "idx_outbox_aggregate", columnList = "aggregate_type,aggregate_id")
})
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class OutboxEvent {
    @Id
    @Column(length = 36)
    private String id;
    @Column(name = "aggregate_type", nullable = false, length = 50)
    private String aggregateType;
    @Column(name = "aggregate_id", nullable = false)
    private Long aggregateId;
    @Column(nullable = false, length = 200)
    private String topic;
    @Column(nullable = false, columnDefinition = "TEXT")
    private String payload;
    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private Status status;
    @Column(nullable = false)
    private int attempts;
    @Column(name = "next_attempt_at", nullable = false)
    private Instant nextAttemptAt;
    @Column(name = "locked_until")
    private Instant lockedUntil;
    @Column(name = "last_error", columnDefinition = "TEXT")
    private String lastError;
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;
    @Column(name = "published_at")
    private Instant publishedAt;

    public enum Status { PENDING, PROCESSING, PUBLISHED, DEAD }
}

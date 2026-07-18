package com.smartdoc.document.service;

import com.smartdoc.document.model.OutboxEvent;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.rocketmq.spring.core.RocketMQTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Duration;

/** 将已提交的 Outbox 事件可靠投递给 RocketMQ。 */
@Slf4j
@Component
@RequiredArgsConstructor
public class OutboxPublisher {
    private final OutboxService outboxService;
    private final RocketMQTemplate rocketMQTemplate;
    @Value("${outbox.batch-size:50}") private int batchSize;
    @Value("${outbox.max-attempts:10}") private int maxAttempts;

    @Scheduled(fixedDelayString = "${outbox.poll-interval-ms:1000}")
    public void publishPendingEvents() {
        for (String id : outboxService.claimBatch(batchSize, Duration.ofMinutes(5))) {
            OutboxEvent event = outboxService.get(id);
            if (event == null || event.getStatus() != OutboxEvent.Status.PROCESSING) continue;
            try {
                rocketMQTemplate.convertAndSend(event.getTopic(), event.getPayload());
                outboxService.markPublished(id);
            } catch (Exception error) {
                log.warn("Outbox publish failed, eventId={}", id, error);
                boolean dead = outboxService.reschedule(id, error.getMessage(), maxAttempts);
                if (dead) {
                    try { rocketMQTemplate.convertAndSend(event.getTopic() + "-dlq", event.getPayload()); }
                    catch (Exception dlqError) { log.error("Outbox DLQ publish failed, eventId={}", id, dlqError); }
                }
            }
        }
    }
}

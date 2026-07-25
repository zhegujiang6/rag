package com.smartdoc.document.service;

import com.smartdoc.document.model.OutboxEvent;
import com.smartdoc.document.repository.OutboxEventRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class OutboxService {
    private final OutboxEventRepository repository;

    /** 必须与 Document 保存处于同一事务。 */
    @Transactional
    public void enqueueDocumentProcessing(Long documentId) {
        Instant now = Instant.now();
        repository.save(OutboxEvent.builder()
                .id(UUID.randomUUID().toString()).aggregateType("DOCUMENT").aggregateId(documentId)
                .topic("doc-process-topic").payload(documentId.toString())
                .status(OutboxEvent.Status.PENDING).attempts(0).nextAttemptAt(now).createdAt(now).build());
    }

    @Transactional
    public List<String> claimBatch(int batchSize, Duration lease) {
        Instant now = Instant.now();
        List<OutboxEvent> events = repository.lockDispatchable(
                now, OutboxEvent.Status.PENDING, OutboxEvent.Status.PROCESSING, PageRequest.of(0, batchSize));
        Instant lockedUntil = now.plus(lease);
        events.forEach(event -> { event.setStatus(OutboxEvent.Status.PROCESSING); event.setLockedUntil(lockedUntil); });
        return events.stream().map(OutboxEvent::getId).toList();
    }

    @Transactional
    public OutboxEvent get(String id) { return repository.findById(id).orElse(null); }

    @Transactional
    public void markPublished(String id) {
        repository.findById(id).ifPresent(event -> {
            event.setStatus(OutboxEvent.Status.PUBLISHED); event.setPublishedAt(Instant.now()); event.setLockedUntil(null);
        });
    }

    @Transactional
    public boolean reschedule(String id, String error, int maxAttempts) {
        OutboxEvent event = repository.findById(id).orElse(null);
        if (event == null) return false;
        {
            int attempts = event.getAttempts() + 1;
            event.setAttempts(attempts); event.setLastError(error); event.setLockedUntil(null);
            if (attempts >= maxAttempts) { event.setStatus(OutboxEvent.Status.DEAD); return true; }
            else { event.setStatus(OutboxEvent.Status.PENDING); event.setNextAttemptAt(Instant.now().plusSeconds(Math.min(300, 1L << Math.min(attempts, 8)))); }
        }
        return false;
    }
}

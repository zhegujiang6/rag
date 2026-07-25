package com.smartdoc.document.repository;

import com.smartdoc.document.model.OutboxEvent;
import jakarta.persistence.LockModeType;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;

import java.time.Instant;
import java.util.List;

public interface OutboxEventRepository extends JpaRepository<OutboxEvent, String> {
    /** 多副本发布器通过悲观锁领取任务；锁过期的 PROCESSING 事件可被恢复。 */
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select e from OutboxEvent e where e.nextAttemptAt <= :now and " +
           "(e.status = :pending or (e.status = :processing and e.lockedUntil < :now)) order by e.createdAt")
    List<OutboxEvent> lockDispatchable(Instant now, OutboxEvent.Status pending,
                                       OutboxEvent.Status processing, Pageable pageable);
}

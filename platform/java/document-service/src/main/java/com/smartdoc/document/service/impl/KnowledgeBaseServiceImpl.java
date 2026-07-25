package com.smartdoc.document.service.impl;

import com.smartdoc.common.exception.BusinessException;
import com.smartdoc.common.exception.ErrorCode;
import com.smartdoc.document.dto.KbCreateRequest;
import com.smartdoc.document.dto.KbResponse;
import com.smartdoc.document.model.Document;
import com.smartdoc.document.model.KnowledgeBase;
import com.smartdoc.document.repository.DocumentRepository;
import com.smartdoc.document.repository.KnowledgeBaseRepository;
import com.smartdoc.document.service.KnowledgeBaseService;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.Instant;
import java.util.List;

@Service
@RequiredArgsConstructor
public class KnowledgeBaseServiceImpl implements KnowledgeBaseService {
    private final KnowledgeBaseRepository kbRepository;
    private final DocumentRepository documentRepository;
    @Override @Transactional
    public KbResponse create(KbCreateRequest request, Long userId) {
        KnowledgeBase kb = kbRepository.save(KnowledgeBase.builder().userId(userId).name(request.getName().trim()).description(request.getDescription()).isDefault(false).createdAt(Instant.now()).updatedAt(Instant.now()).build());
        return toResponse(kb);
    }
    @Override @Transactional(readOnly = true)
    public List<KbResponse> listByUser(Long userId) { return kbRepository.findByUserIdOrderByCreatedAtDesc(userId).stream().map(this::toResponse).toList(); }
    @Override @Transactional(readOnly = true)
    public KbResponse get(Long kbId, Long userId) { return toResponse(requireKb(kbId, userId)); }
    @Override @Transactional
    public void delete(Long kbId, Long userId) { kbRepository.delete(requireKb(kbId, userId)); }
    @Override @Transactional
    public void addDocument(Long kbId, Long docId, Long userId) { Document document = requireDocument(docId, userId); document.setKnowledgeBaseId(requireKb(kbId, userId).getId()); documentRepository.save(document); }
    @Override @Transactional
    public void removeDocument(Long kbId, Long docId, Long userId) { Document document = requireDocument(docId, userId); if (!kbId.equals(document.getKnowledgeBaseId())) throw new BusinessException(ErrorCode.DOCUMENT_NOT_FOUND); document.setKnowledgeBaseId(null); documentRepository.save(document); }
    private KnowledgeBase requireKb(Long id, Long userId) { return kbRepository.findByIdAndUserId(id, userId).orElseThrow(() -> new BusinessException(ErrorCode.KB_NOT_FOUND)); }
    private Document requireDocument(Long id, Long userId) { return documentRepository.findByIdAndUserId(id, userId).orElseThrow(() -> new BusinessException(ErrorCode.DOCUMENT_NOT_FOUND)); }
    private KbResponse toResponse(KnowledgeBase kb) { return KbResponse.builder().id(kb.getId()).name(kb.getName()).description(kb.getDescription()).createdAt(kb.getCreatedAt()).documentCount(0).chunkCount(0).build(); }
}

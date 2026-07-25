package com.smartdoc.document.service.impl;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartdoc.common.dto.PageResult;
import com.smartdoc.common.exception.BusinessException;
import com.smartdoc.common.exception.ErrorCode;
import com.smartdoc.document.dto.DocumentResponse;
import com.smartdoc.document.dto.DocumentUploadResponse;
import com.smartdoc.document.dto.ProcessStatusResponse;
import com.smartdoc.document.model.Document;
import com.smartdoc.document.repository.DocumentRepository;
import com.smartdoc.document.repository.KnowledgeBaseRepository;
import com.smartdoc.document.service.DocumentService;
import com.smartdoc.document.service.OutboxService;
import io.minio.MinioClient;
import io.minio.BucketExistsArgs;
import io.minio.MakeBucketArgs;
import io.minio.PutObjectArgs;
import io.minio.RemoveObjectArgs;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;
import java.io.InputStream;
import java.net.URI;
import java.time.Instant;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class DocumentServiceImpl implements DocumentService {
    private static final Set<String> ALLOWED_TYPES = Set.of("txt", "md", "pdf", "doc", "docx");
    private final DocumentRepository repository;
    private final KnowledgeBaseRepository kbRepository;
    private final MinioClient minioClient;
    private final ObjectMapper objectMapper;
    private final OutboxService outboxService;
    @Value("${minio.bucket}") private String bucket;

    @Override @Transactional
    public DocumentUploadResponse upload(MultipartFile file, Long kbId, Long userId) {
        if (file == null || file.isEmpty()) throw new BusinessException(ErrorCode.PARAM_INVALID);
        String original = safeFilename(file.getOriginalFilename());
        String type = extension(original);
        if (!ALLOWED_TYPES.contains(type)) throw new BusinessException(ErrorCode.FILE_FORMAT_UNSUPPORTED);
        if (kbId != null && !kbRepository.existsById(kbId)) throw new BusinessException(ErrorCode.KB_NOT_FOUND);
        String objectName = userId + "/" + UUID.randomUUID() + "." + type;
        try (InputStream in = file.getInputStream()) {
            if (!minioClient.bucketExists(BucketExistsArgs.builder().bucket(bucket).build())) {
                minioClient.makeBucket(MakeBucketArgs.builder().bucket(bucket).build());
            }
            minioClient.putObject(PutObjectArgs.builder().bucket(bucket).object(objectName).stream(in, file.getSize(), -1).contentType(file.getContentType()).build());
        } catch (Exception e) { throw new BusinessException(ErrorCode.DOC_PROCESS_FAILED); }
        Document document = repository.save(Document.builder().userId(userId).knowledgeBaseId(kbId).filename(objectName).originalFilename(original)
                .fileType(type).fileSize(file.getSize()).filePath(objectName).sourceType("file").status(Document.DocStatus.uploading).chunkCount(0).tags("[]").createdAt(Instant.now()).build());
        outboxService.enqueueDocumentProcessing(document.getId());
        return uploadResponse(document);
    }

    @Override @Transactional
    public DocumentUploadResponse importUrl(String url, Long kbId, Long userId) {
        try { URI uri = URI.create(url); if (!("http".equalsIgnoreCase(uri.getScheme()) || "https".equalsIgnoreCase(uri.getScheme())) || uri.getHost() == null) throw new IllegalArgumentException(); }
        catch (IllegalArgumentException e) { throw new BusinessException(ErrorCode.PARAM_INVALID); }
        if (repository.existsBySourceUrlAndUserId(url, userId)) throw new BusinessException(ErrorCode.URL_ALREADY_EXISTS);
        if (kbId != null && !kbRepository.existsById(kbId)) throw new BusinessException(ErrorCode.KB_NOT_FOUND);
        Document document = repository.save(Document.builder().userId(userId).knowledgeBaseId(kbId).filename("url-" + UUID.randomUUID()).originalFilename(url)
                .fileType("html").sourceType("web").sourceUrl(url).status(Document.DocStatus.uploading).chunkCount(0).tags("[]").createdAt(Instant.now()).build());
        outboxService.enqueueDocumentProcessing(document.getId());
        return uploadResponse(document);
    }

    @Override @Transactional(readOnly = true)
    public ProcessStatusResponse getProcessStatus(Long documentId, Long userId) {
        Document d = require(documentId, userId);
        int progress = switch (d.getStatus()) { case uploading -> 0; case parsing -> 20; case chunking -> 45; case embedding -> 75; case completed, failed -> 100; };
        return ProcessStatusResponse.builder().documentId(d.getId()).status(d.getStatus().name()).errorMessage(d.getErrorMessage()).chunkCount(d.getChunkCount()).progress(progress).build();
    }

    @Override @Transactional(readOnly = true)
    public PageResult<DocumentResponse> list(Long kbId, int page, int size, Long userId) {
        if (page < 1 || size < 1 || size > 100) throw new BusinessException(ErrorCode.PARAM_INVALID);
        PageRequest pageable = PageRequest.of(page - 1, size, Sort.by(Sort.Direction.DESC, "createdAt"));
        Page<Document> result = kbId == null ? repository.findByUserId(userId, pageable) : repository.findByUserIdAndKnowledgeBaseId(userId, kbId, pageable);
        return PageResult.<DocumentResponse>builder().records(result.getContent().stream().map(this::toResponse).toList()).total(result.getTotalElements()).page(page).size(size).totalPages(result.getTotalPages()).build();
    }

    @Override @Transactional(readOnly = true)
    public DocumentResponse get(Long documentId, Long userId) { return toResponse(require(documentId, userId)); }

    @Override @Transactional
    public void deleteDocument(Long documentId, Long userId) {
        Document d = require(documentId, userId);
        if (d.getFilePath() != null) try { minioClient.removeObject(RemoveObjectArgs.builder().bucket(bucket).object(d.getFilePath()).build()); } catch (Exception ignored) { }
        repository.delete(d);
    }
    @Override @Transactional public void addTag(Long id, String tag, Long userId) { updateTags(require(id, userId), tag, true); }
    @Override @Transactional public void removeTag(Long id, String tag, Long userId) { updateTags(require(id, userId), tag, false); }
    private void updateTags(Document d, String tag, boolean add) {
        if (tag == null || tag.isBlank() || tag.length() > 50) throw new BusinessException(ErrorCode.PARAM_INVALID);
        try { List<String> tags = objectMapper.readValue(d.getTags() == null ? "[]" : d.getTags(), new TypeReference<>() {}); if (add && !tags.contains(tag)) tags.add(tag); if (!add) tags.remove(tag); d.setTags(objectMapper.writeValueAsString(tags)); repository.save(d); }
        catch (Exception e) { throw new BusinessException(ErrorCode.PARAM_INVALID); }
    }
    private Document require(Long id, Long userId) { return repository.findByIdAndUserId(id, userId).orElseThrow(() -> new BusinessException(ErrorCode.DOCUMENT_NOT_FOUND)); }
    private DocumentUploadResponse uploadResponse(Document d) { return DocumentUploadResponse.builder().documentId(d.getId()).filename(d.getOriginalFilename()).status(d.getStatus().name()).message("Document accepted for processing").build(); }
    private DocumentResponse toResponse(Document d) { return DocumentResponse.builder().id(d.getId()).originalFilename(d.getOriginalFilename()).fileType(d.getFileType()).fileSize(d.getFileSize()).sourceType(d.getSourceType()).sourceUrl(d.getSourceUrl()).status(d.getStatus().name()).chunkCount(d.getChunkCount()).tags(d.getTags()).createdAt(d.getCreatedAt()).build(); }
    private String safeFilename(String name) { if (name == null || name.isBlank()) throw new BusinessException(ErrorCode.PARAM_INVALID); return name.replace('\\', '_').replace('/', '_'); }
    private String extension(String name) { int dot = name.lastIndexOf('.'); return dot < 1 ? "" : name.substring(dot + 1).toLowerCase(Locale.ROOT); }
}

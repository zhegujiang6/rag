package com.smartdoc.document.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartdoc.document.model.Document;
import com.smartdoc.document.model.ParentChunk;
import com.smartdoc.document.model.SubChunk;
import com.smartdoc.document.repository.DocumentRepository;
import com.smartdoc.document.repository.ParentChunkRepository;
import com.smartdoc.document.repository.SubChunkRepository;
import io.minio.GetObjectArgs;
import io.minio.MinioClient;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.rocketmq.spring.annotation.RocketMQMessageListener;
import org.apache.rocketmq.spring.core.RocketMQListener;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.client.RestClient;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@Slf4j
@Component
@RequiredArgsConstructor
@RocketMQMessageListener(topic = "doc-process-topic", consumerGroup = "doc-process-consumer", maxReconsumeTimes = 5)
public class PipelineService implements RocketMQListener<String> {
    private final DocumentRepository documentRepository;
    private final ParentChunkRepository parentRepository;
    private final SubChunkRepository subRepository;
    private final MinioClient minioClient;
    private final ObjectMapper objectMapper;
    @Value("${minio.bucket}") private String bucket;
    @Value("${embedding.api-base:https://api.openai.com/v1}") private String embeddingBase;
    @Value("${embedding.api-key:}") private String embeddingKey;
    @Value("${embedding.model:text-embedding-3-small}") private String embeddingModel;
    @Value("${chromadb.base-url:http://127.0.0.1:8001}") private String chromaBase;

    @Override
    @Transactional
    public void onMessage(String message) {
        Long id = Long.valueOf(message);
        Document document = documentRepository.findByIdForProcessing(id).orElse(null);
        // completed 表示已成功处理；其它处理中状态说明重复消息已被另一消费者领取。
        if (document == null || document.getStatus() == Document.DocStatus.completed) return;
        if (document.getStatus() == Document.DocStatus.parsing || document.getStatus() == Document.DocStatus.chunking || document.getStatus() == Document.DocStatus.embedding) return;
        try {
            document.setStatus(Document.DocStatus.parsing);
            documentRepository.save(document);
            String text = extract(document);
            if (text.isBlank()) throw new IllegalArgumentException("No extractable text");
            document.setStatus(Document.DocStatus.chunking);
            List<String> parents = split(text, 2200, 250);
            List<ParentChunk> savedParents = new ArrayList<>();
            for (int i = 0; i < parents.size(); i++) savedParents.add(parentRepository.save(ParentChunk.builder().documentId(id).userId(document.getUserId()).chunkIndex(i).content(parents.get(i)).tokenCount(parents.get(i).length() / 4).createdAt(Instant.now()).build()));
            List<SubChunk> subChunks = new ArrayList<>();
            for (ParentChunk parent : savedParents) for (String content : split(parent.getContent(), 700, 100)) subChunks.add(SubChunk.builder().parentChunkId(parent.getId()).documentId(id).userId(document.getUserId()).chunkIndex(subChunks.size()).content(content).tokenCount(content.length() / 4).chromaId("doc-" + id + "-" + subChunks.size()).createdAt(Instant.now()).build());
            document.setStatus(Document.DocStatus.embedding);
            subChunks = subRepository.saveAll(subChunks);
            writeVectors(document, subChunks);
            document.setChunkCount(subChunks.size());
            document.setStatus(Document.DocStatus.completed);
            document.setErrorMessage(null);
        } catch (Exception e) {
            log.error("Document processing failed: {}", id, e);
            document.setStatus(Document.DocStatus.failed);
            document.setErrorMessage(e.getMessage());
            documentRepository.save(document);
            // 抛出异常让 RocketMQ 按 maxReconsumeTimes 重试；超限后由 Broker 自动进入 %DLQ%。
            throw new IllegalStateException("Document processing retryable failure: " + id, e);
        }
        documentRepository.save(document);
    }

    private String extract(Document d) throws Exception {
        if ("web".equals(d.getSourceType())) return HttpClient.newHttpClient().send(HttpRequest.newBuilder(URI.create(d.getSourceUrl())).GET().build(), HttpResponse.BodyHandlers.ofString()).body().replaceAll("<[^>]+>", " ");
        if (!("txt".equals(d.getFileType()) || "md".equals(d.getFileType()))) throw new IllegalArgumentException("Only txt and md are supported by the Java worker");
        try (InputStream in = minioClient.getObject(GetObjectArgs.builder().bucket(bucket).object(d.getFilePath()).build())) { return new String(in.readAllBytes(), StandardCharsets.UTF_8); }
    }
    private List<String> split(String text, int size, int overlap) { List<String> out = new ArrayList<>(); for (int start = 0; start < text.length(); start += size - overlap) { out.add(text.substring(start, Math.min(text.length(), start + size))); if (start + size >= text.length()) break; } return out; }
    private void writeVectors(Document d, List<SubChunk> chunks) throws Exception {
        if (embeddingKey.isBlank()) throw new IllegalStateException("EMBEDDING_API_KEY is not configured");
        List<String> inputs = chunks.stream().map(SubChunk::getContent).toList();
        JsonNode response = RestClient.create(embeddingBase).post().uri("/embeddings").contentType(MediaType.APPLICATION_JSON).header("Authorization", "Bearer " + embeddingKey).body(Map.of("model", embeddingModel, "input", inputs)).retrieve().body(JsonNode.class);
        List<List<Double>> vectors = new ArrayList<>(); for (JsonNode item : response.path("data")) { List<Double> vector = new ArrayList<>(); item.path("embedding").forEach(n -> vector.add(n.asDouble())); vectors.add(vector); }
        List<Map<String, Object>> payload = new ArrayList<>(); for (SubChunk c : chunks) payload.add(Map.of("chroma_id", c.getChromaId(), "content", c.getContent(), "metadata", Map.of("document_id", c.getDocumentId(), "parent_chunk_id", c.getParentChunkId(), "chunk_index", c.getChunkIndex(), "user_id", c.getUserId())));
        RestClient.create(chromaBase).post().uri("/api/v1/collections/kb-" + (d.getKnowledgeBaseId() == null ? "default" : d.getKnowledgeBaseId()) + "/add").contentType(MediaType.APPLICATION_JSON).body(Map.of("collection_name", "ignored", "chunks", payload, "embeddings", vectors)).retrieve().toBodilessEntity();
    }
}

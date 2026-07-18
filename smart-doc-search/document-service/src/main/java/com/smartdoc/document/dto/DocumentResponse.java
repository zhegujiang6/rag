package com.smartdoc.document.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

/**
 * 文档列表响应 DTO。
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class DocumentResponse {

    private Long id;
    private String originalFilename;
    private String fileType;
    private Long fileSize;
    private String sourceType;
    private String sourceUrl;
    private String status;
    private Integer chunkCount;
    private Object tags;
    private Instant createdAt;
}

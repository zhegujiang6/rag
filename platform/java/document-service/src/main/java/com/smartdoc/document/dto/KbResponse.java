package com.smartdoc.document.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

/**
 * 知识库响应 DTO。
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class KbResponse {

    private Long id;
    private String name;
    private String description;
    private Integer chunkCount;
    private Integer documentCount;
    private Instant createdAt;
}

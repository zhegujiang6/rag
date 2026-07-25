package com.smartdoc.document.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 文档处理进度响应。
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ProcessStatusResponse {

    private Long documentId;
    private String status;       // uploading / parsing / chunking / embedding / completed / failed
    private String errorMessage;
    private Integer chunkCount;
    private Integer progress;    // 0-100
}

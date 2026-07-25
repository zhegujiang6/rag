package com.smartdoc.document.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 文档上传/导入响应。
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class DocumentUploadResponse {

    private Long documentId;
    private String filename;
    private String status;
    private String message;
}

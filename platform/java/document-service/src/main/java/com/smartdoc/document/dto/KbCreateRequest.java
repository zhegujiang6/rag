package com.smartdoc.document.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 知识库创建请求。
 */
@Data
public class KbCreateRequest {

    @NotBlank(message = "知识库名称不能为空")
    @Size(max = 200, message = "名称最长200个字符")
    private String name;

    private String description;
}

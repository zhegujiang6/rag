package com.smartdoc.common.exception;

import lombok.Getter;

/**
 * 统一错误码枚举。
 */
@Getter
public enum ErrorCode {

    // ── 通用 (1xxx) ──
    SUCCESS(0, "成功"),
    UNKNOWN_ERROR(1000, "未知错误"),
    PARAM_INVALID(1001, "参数校验失败"),
    RATE_LIMITED(1002, "请求频率过高，请稍后再试"),

    // ── 用户/认证 (2xxx) ──
    UNAUTHORIZED(2001, "未登录或 Token 已过期"),
    FORBIDDEN(2002, "无权限访问"),
    USER_NOT_FOUND(2003, "用户不存在"),
    PASSWORD_ERROR(2004, "密码错误"),
    USERNAME_EXISTS(2005, "用户名已存在"),
    TOKEN_EXPIRED(2006, "Token 已过期"),
    TOKEN_INVALID(2007, "Token 无效"),

    // ── 文档/知识库 (3xxx) ──
    DOCUMENT_NOT_FOUND(3001, "文档不存在"),
    KB_NOT_FOUND(3002, "知识库不存在"),
    FILE_TOO_LARGE(3003, "文件大小超出限制"),
    FILE_FORMAT_UNSUPPORTED(3004, "不支持的文件格式"),
    DOC_PROCESS_FAILED(3005, "文档处理失败"),
    URL_ALREADY_EXISTS(3006, "该 URL 已导入"),

    // ── RAG/LLM (4xxx) ──
    SEARCH_FAILED(4001, "检索失败"),
    LLM_CALL_FAILED(4002, "LLM 调用失败"),
    EMBEDDING_FAILED(4003, "向量化失败"),
    RERANK_FAILED(4004, "重排序失败"),
    LLM_RATE_LIMITED(4005, "LLM 调用频率超限"),
    LLM_TIMEOUT(4006, "LLM 响应超时"),

    // ── 评测 (5xxx) ──
    EVAL_RUN_NOT_FOUND(5001, "评测记录不存在"),
    EVAL_DATASET_EMPTY(5002, "测试数据集为空"),
    ;

    private final int code;
    private final String message;

    ErrorCode(int code, String message) {
        this.code = code;
        this.message = message;
    }
}

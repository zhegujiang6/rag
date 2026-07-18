package com.smartdoc.common.util;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

/**
 * 哈希工具类 — SHA256 摘要，用于缓存 Key 生成。
 */
public final class HashUtil {

    private HashUtil() {}

    /**
     * 计算文本的 SHA256 哈希 (Hex 字符串)。
     * <p>用于 Redis 缓存 Key，避免 Key 过长。
     */
    public static String sha256(String text) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] digest = md.digest(text.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            for (byte b : digest) {
                sb.append(String.format("%02x", b));
            }
            return sb.toString();
        } catch (NoSuchAlgorithmException e) {
            throw new RuntimeException("SHA-256 algorithm not available", e);
        }
    }

    /** 计算文本的 SHA256 前 N 位 (节省 Key 空间) */
    public static String sha256Short(String text, int length) {
        return sha256(text).substring(0, Math.min(length, 64));
    }
}

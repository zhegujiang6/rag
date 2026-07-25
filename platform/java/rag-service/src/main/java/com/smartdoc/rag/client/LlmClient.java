package com.smartdoc.rag.client;

import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;

import java.util.List;
import java.util.Map;

/**
 * LLM API 客户端 — 封装 OpenAI 兼容的 LLM 调用 (WebFlux 非阻塞)。
 *
 * <p>支持：
 * <ul>
 *   <li>流式 SSE 聊天补全</li>
 *   <li>同步聊天补全 (用于评测/重排序)</li>
 *   <li>自动重试 + 熔断降级 (Resilience4j)</li>
 * </ul>
 */
public class LlmClient {

    private final WebClient webClient;

    public LlmClient(WebClient.Builder builder, String apiBase, String apiKey) {
        this.webClient = builder
                .baseUrl(apiBase)
                .defaultHeader("Authorization", "Bearer " + apiKey)
                .build();
    }

    /**
     * 流式聊天补全 (SSE)。
     *
     * @param messages    消息列表 [{"role":"system","content":"..."}, ...]
     * @param temperature 温度参数
     * @param maxTokens   最大 token 数
     * @return Flux 逐 token 流
     */
    public Flux<String> chatStream(List<Map<String, String>> messages,
                                   double temperature, int maxTokens) {
        // TODO: 实现 WebFlux SSE 流式解析
        return Flux.empty();
    }

    /**
     * 同步聊天补全 (阻塞，用于重排序/评测)。
     *
     * @return 完整响应文本
     */
    public String chatSync(List<Map<String, String>> messages,
                           double temperature, int maxTokens) {
        // TODO: 实现同步调用
        return "";
    }
}

package com.smartdoc.gateway.config;

import org.springframework.cloud.gateway.filter.ratelimit.KeyResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Redis 分布式限流的用户维度 Key；未登录请求按来源 IP 限制。 */
@Configuration
public class RateLimitConfig {
    @Bean
    public KeyResolver userKeyResolver() {
        return exchange -> {
            String userId = exchange.getRequest().getHeaders().getFirst("X-User-Id");
            if (userId != null && !userId.isBlank()) return reactor.core.publisher.Mono.just("user:" + userId);
            String host = exchange.getRequest().getRemoteAddress() == null ? "unknown"
                    : exchange.getRequest().getRemoteAddress().getAddress().getHostAddress();
            return reactor.core.publisher.Mono.just("ip:" + host);
        };
    }
}

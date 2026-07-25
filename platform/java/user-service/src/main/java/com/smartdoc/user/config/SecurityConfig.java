package com.smartdoc.user.config;

import com.smartdoc.common.filter.UserContextFilter;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

/**
 * 安全配置 — Spring Security 仅用于提供 PasswordEncoder。
 *
 * <p>认证在 Gateway 层完成，user-service 不做 Token 校验，
 * 而是信任 Gateway 传递的 X-User-Id / X-Username Header。
 */
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    /**
     * BCrypt 密码编码器。
     */
    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    /**
     * 禁用 Spring Security 的表单登录和 CSRF，
     * 放行所有请求（认证由 Gateway 处理）。
     */
    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(sm -> sm.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
            .formLogin(f -> f.disable())
            .httpBasic(b -> b.disable());
        return http.build();
    }

    /**
     * 注册 UserContextFilter — 从 Header 提取当前用户信息。
     */
    @Bean
    public FilterRegistrationBean<UserContextFilter> userContextFilterReg() {
        FilterRegistrationBean<UserContextFilter> reg = new FilterRegistrationBean<>();
        reg.setFilter(new UserContextFilter());
        reg.addUrlPatterns("/api/*");
        reg.setOrder(1);
        return reg;
    }
}

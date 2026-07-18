package com.smartdoc.rag.config;

import com.smartdoc.common.filter.UserContextFilter;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Web 配置 — 注册 UserContextFilter。
 */
@Configuration
public class WebConfig {

    @Bean
    public FilterRegistrationBean<UserContextFilter> userContextFilterReg() {
        FilterRegistrationBean<UserContextFilter> reg = new FilterRegistrationBean<>();
        reg.setFilter(new UserContextFilter());
        reg.addUrlPatterns("/api/*");
        reg.setOrder(1);
        return reg;
    }
}

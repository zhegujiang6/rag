package com.smartdoc.common.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

/**
 * 分页查询统一响应。
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class PageResult<T> {

    /** 当前页数据 */
    private List<T> records;

    /** 总记录数 */
    private long total;

    /** 当前页码 (从1开始) */
    private int page;

    /** 每页大小 */
    private int size;

    /** 总页数 */
    private int totalPages;
}

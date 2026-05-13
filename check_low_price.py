from db_save import query_to_df

# 금천구 최저가 데이터 확인
df = query_to_df("""
    SELECT gu, dong, apt_name, area, floor, price, trade_date
    FROM apt_trade
    WHERE gu = '금천구' AND price <= 15000
    ORDER BY price ASC
    LIMIT 20
""")

if df.empty:
    print("해당 조건의 데이터 없음")
else:
    print(df.to_string())

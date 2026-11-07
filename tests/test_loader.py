import pytest

from core.loader import LoadError, clean_columns, load_csv, table_name_from_filename


def test_semicolon_currency_and_dates():
    t = load_csv("My Sales 2024.csv", b"Order Date;Amount;Region\n2024-01-05;$1,200;N\n2024-02-05;$900;S\n")
    assert t.name == "my_sales_2024"
    assert list(t.df.columns) == ["order_date", "amount", "region"]
    assert str(t.df["order_date"].dtype).startswith("datetime64")
    assert t.df["amount"].tolist() == [1200, 900]


def test_latin1_encoding():
    t = load_csv("c.csv", "name,city\nJosé,Málaga\n".encode("cp1252"))
    assert t.df["name"][0] == "José"


def test_empty_and_wrong_type():
    with pytest.raises(LoadError):
        load_csv("a.csv", b"   ")
    with pytest.raises(LoadError):
        load_csv("a.pdf", b"a,b\n1,2")
    with pytest.raises(LoadError):
        load_csv("a.csv", b"a,b\n,\n,\n")


def test_duplicate_columns_and_names():
    assert clean_columns(["A b", "a_b", "1x"]) == ["a_b", "a_b_2", "c_1x"]
    assert table_name_from_filename("sales.csv", {"sales"}) == "sales_2"
    assert table_name_from_filename("2024 data.csv") == "t_2024_data"


def test_sample_files_load(sales, customers):
    assert len(sales) > 1000 and "revenue" in sales.columns
    assert "customer_id" in customers.columns

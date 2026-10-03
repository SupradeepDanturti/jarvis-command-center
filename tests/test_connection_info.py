from backend.connection_info import FILE_NAME, write_connection_files


def test_code_and_port_refresh_in_both_folders(tmp_path):
    desktop, downloads = tmp_path / 'Desktop', tmp_path / 'Downloads'
    directories = [desktop, downloads]
    addresses = [('Wi-Fi', '192.168.2.12')]
    first = write_connection_files('ABCD1234', 18761, directories, addresses)
    assert len(first) == 2 and all(error is None for _, error in first)
    for directory in directories:
        text = (directory / FILE_NAME).read_text(encoding='utf-8')
        assert 'ABCD1234' in text
        assert 'http://192.168.2.12:18761' in text
    assert write_connection_files('ABCD1234', 18761, directories, addresses) == []
    write_connection_files('NEWCODE1', 18761, directories, [('Wi-Fi', '192.168.2.20')])
    for directory in directories:
        text = (directory / FILE_NAME).read_text(encoding='utf-8')
        assert 'NEWCODE1' in text and 'ABCD1234' not in text
        assert 'http://192.168.2.20:18761' in text


def test_existing_unrelated_file_preserved_and_other_folder_updates(tmp_path):
    desktop, downloads = tmp_path / 'Desktop', tmp_path / 'Downloads'
    desktop.mkdir()
    existing = desktop / FILE_NAME
    existing.write_text('My personal notes', encoding='utf-8')
    results = write_connection_files('ABCD1234', 18761, [desktop, downloads], [])
    assert results[0][1] is not None
    assert existing.read_text(encoding='utf-8') == 'My personal notes'
    assert results[1][1] is None
    assert 'Waiting for Wi-Fi' in (downloads / FILE_NAME).read_text(encoding='utf-8')

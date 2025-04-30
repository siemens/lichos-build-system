import pytest
from lichosrebuildtool import RebuildTool

@pytest.fixture
def rebuild_tool():
    return RebuildTool()

@pytest.fixture
def rebuild_list():
    return [["package1"],
            ["package2"],
            ["package3"],
            ["package3", "package2"],    
    ]

@pytest.fixture
def summaries():
    return {
        "package1.amd64": {
            "source": "package1",
            "bdeps": [
                [
                    "package2",
                    "1.0"
                ],
                [
                    "package3",
                    "1.0"
                ]
            ],
            "binary": [
                "package1",
            ],
            "version": "1.0",
            "arch": "amd64"
        },
        "package2.amd64": {
            "source": "package2",
            "bdeps": [
                [
                    "package4",
                    "1.0"
                ],
                [
                    "package5",
                    "1.0"
                ]
            ],
            "binary": [
                "package2",
            ],
            "version": "2.0",
            "arch": "amd64"
        },
        "package3.amd64": {
            "source": "package3",
            "bdeps": [
                [
                    "package6",
                    "1.0"
                ],
                [
                    "package7",
                    "1.0"
                ]
            ],
            "binary": [
                "package3",
            ],
            "version": "2.0",
            "arch": "amd64"
        },
        "package4.amd64": {
            "source": "package4",
            "bdeps": [
                [
                    "package8",
                    "1.0"
                ],
                [
                    "bar",
                    "1.0"
                ]
            ],
            "binary": [
                "package4",
            ],
            "version": "2.0",
            "arch": "amd64"
        },
        "package5.amd64": {
            "source": "package5",
            "bdeps": [
                [
                    "foo",
                    "1.0"
                ],
                [
                    "bar",
                    "1.0"
                ]
            ],
            "binary": [
                "package5",
            ],
            "version": "2.0",
            "arch": "amd64"
        },
        "package6.amd64": {
            "source": "package6",
            "bdeps": [
                [
                    "foo",
                    "1.0"
                ],
                [
                    "bar",
                    "1.0"
                ]
            ],
            "binary": [
                "package6",
            ],
            "version": "2.0",
            "arch": "amd64"
        },
        "package7.amd64": {
            "source": "package7",
            "bdeps": [
                [
                    "foo",
                    "1.0"
                ],
                [
                    "bar",
                    "1.0"
                ]
            ],
            "binary": [
                "package7",
            ],
            "version": "2.0",
            "arch": "amd64"
        },
        "package8.amd64": {
            "source": "package8",
            "bdeps": [
                [
                    "foo",
                    "1.0"
                ],
                [
                    "bar",
                    "1.0"
                ]
            ],
            "binary": [
                "package8",
            ],
            "version": "2.0",
            "arch": "amd64"
        },
    }

@pytest.fixture
def summaries_different_arch():
    return {
        "package1.amd64": {
            "source": "package1",
            "bdeps": [
                [
                    "package2",
                    "1.0"
                ],
                [
                    "package3",
                    "1.0"
                ]
            ],
            "binary": [
                "package1",
            ],
            "version": "1.0",
            "arch": "amd64"
        },
        "package2.amd64": {
            "source": "package2",
            "bdeps": [
                [
                    "foo",
                    "1.0"
                ],
                [
                    "bar",
                    "1.0"
                ]
            ],
            "binary": [
                "package2",
            ],
            "version": "2.0",
            "arch": "amd64"
        },
        "package3.arm64": {
            "source": "package3",
            "bdeps": [
                [
                    "foo",
                    "1.0"
                ],
                [
                    "bar",
                    "1.0"
                ]
            ],
            "binary": [
                "package3",
            ],
            "version": "2.0",
            "arch": "arm64"
        }
    }

@pytest.fixture
def current_package_build_status_all_success():
    return {
    "package1": "success",
    "package2": "success",
    "package3": "success"
    }

def test_extract_sources(rebuild_tool, summaries):
    sources = rebuild_tool._extract_sources(summaries)
    assert sources == {
        "package1": "package1",
        "package2": "package2",
        "package3": "package3",
        "package4": "package4",
        "package5": "package5",
        "package6": "package6",
        "package7": "package7",
        "package8": "package8"
    }

def test_determine_source_dependencies(rebuild_tool, summaries):
    sources = rebuild_tool._extract_sources(summaries)
    source_deps = rebuild_tool._determine_source_dependencies(summaries, sources)
    assert source_deps == {
        'package1': {'package2': {}, 'package3': {}},
        'package2': {'package4': {}, 'package5': {}},
        'package3': {'package6': {}, 'package7': {}},
        'package4': {'package8': {}},
        'package5': {},
        'package6': {},
        'package7': {},
        'package8': {}
    }

def test_ctree(rebuild_tool, summaries_different_arch):
    rebuild_list, mismatch_list, _ = rebuild_tool._ctree(summaries_different_arch)
    assert rebuild_list == ['package1']
    assert mismatch_list == [('package1.amd64', 'package2', '2.0', '1.0')]

def test_determine_root_packages(rebuild_tool, summaries):
    sources = rebuild_tool._extract_sources(summaries)
    source_deps = rebuild_tool._determine_source_dependencies(summaries, sources)
    root_packages = rebuild_tool._determine_root_packages(source_deps)
    assert root_packages == ['package1']

def test_build_trees(rebuild_tool, summaries):
    sources = rebuild_tool._extract_sources(summaries)
    source_deps = rebuild_tool._determine_source_dependencies(summaries, sources)
    root_packages = rebuild_tool._determine_root_packages(source_deps)
    build_trees = rebuild_tool._build_trees(root_packages, source_deps)
    assert build_trees == {
        'package1': {'package2': {'package4': {'package8': {}},'package5': {}},
                     'package3': {'package6': {},'package7': {}}}
        }
    
def test_find_key_paths_1(rebuild_tool, summaries, rebuild_list):
    sources = rebuild_tool._extract_sources(summaries)
    source_deps = rebuild_tool._determine_source_dependencies(summaries, sources)
    root_packages = rebuild_tool._determine_root_packages(source_deps)
    build_trees = rebuild_tool._build_trees(root_packages, source_deps)
    key_paths = rebuild_tool._find_key_paths(build_trees, rebuild_list[0])
    assert key_paths == [['package1']]

def test_find_key_paths_2(rebuild_tool, summaries, rebuild_list):
    sources = rebuild_tool._extract_sources(summaries)
    source_deps = rebuild_tool._determine_source_dependencies(summaries, sources)
    root_packages = rebuild_tool._determine_root_packages(source_deps)
    build_trees = rebuild_tool._build_trees(root_packages, source_deps)
    key_paths = rebuild_tool._find_key_paths(build_trees, rebuild_list[1])
    assert key_paths == [['package2', 'package1']]

def test_find_key_paths_3(rebuild_tool, summaries, rebuild_list):
    sources = rebuild_tool._extract_sources(summaries)
    source_deps = rebuild_tool._determine_source_dependencies(summaries, sources)
    root_packages = rebuild_tool._determine_root_packages(source_deps)
    build_trees = rebuild_tool._build_trees(root_packages, source_deps)
    key_paths = rebuild_tool._find_key_paths(build_trees, rebuild_list[2])
    assert key_paths == [['package3', 'package1']]

def test_merge_path_lists1(rebuild_tool, summaries, rebuild_list):
    sources = rebuild_tool._extract_sources(summaries)
    source_deps = rebuild_tool._determine_source_dependencies(summaries, sources)
    root_packages = rebuild_tool._determine_root_packages(source_deps)
    build_trees = rebuild_tool._build_trees(root_packages, source_deps)
    key_paths = rebuild_tool._find_key_paths(build_trees, rebuild_list[3])
    merged_paths = rebuild_tool._merge_path_lists(key_paths)
    assert merged_paths == [['package2', 'package3'], ['package1']]

def test_merge_path_lists2(rebuild_tool, summaries, rebuild_list):
    sources = rebuild_tool._extract_sources(summaries)
    source_deps = rebuild_tool._determine_source_dependencies(summaries, sources)
    root_packages = rebuild_tool._determine_root_packages(source_deps)
    build_trees = rebuild_tool._build_trees(root_packages, source_deps)
    key_paths = rebuild_tool._find_key_paths(build_trees, rebuild_list[2])
    merged_paths = rebuild_tool._merge_path_lists(key_paths)
    assert merged_paths == [['package3'], ['package1']]

def test_buildlist(rebuild_tool, rebuild_list, summaries):
    buildlist = rebuild_tool._buildlist(rebuild_list[3], summaries)
    assert buildlist == [['package2', 'package3'], ['package1']]
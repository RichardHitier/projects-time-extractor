from unittest import skip

from web.tools.histories import repo_to_df, hours_per_day, pomo_minutes, merge_all_histories, project_to_df, \
    daily_commits, pomofocus_to_df


def test_repo_to_df():
    project_git_dir = "/home/richard/01DEV/CalipsoProject/calipso-dispatcher-clients/.git"
    df = repo_to_df(project_git_dir)
    print(df.head(20))
    assert True


def test_project_to_df():
    df = project_to_df("calipso")
    print(df)
    assert True


def test_daily_commit():
    git_df = project_to_df("calipso")
    df = daily_commits(git_df)
    print(df)
    # assert len(df) == 58
    assert True


def test_hours_per_day():
    git_df = project_to_df("calipso")
    df = hours_per_day(git_df)
    print(df)
    # assert len(df) == 58
    assert True


def test_pomofocus_to_df(pomofocus_file):
    pom_df = pomofocus_to_df(pomofocus_file)
    print(pom_df.main_project.drop_duplicates())


def test_pomo_minutes(pomofocus_file):
    df = pomo_minutes("calipso", pomofocus_to_df(pomofocus_file))
    print(df)
    # assert len(df) == 58
    assert True


def test_merge_histories(pomofocus_file):
    df = merge_all_histories(pomofocus_to_df(pomofocus_file))
    import pandas as pd
    pd.set_option('display.max_rows', None)
    print(df)
    assert True


@skip("Requires actual data files, not suitable for automated testing")
def test_merge_with_no_git():
    # git_df = project_to_df("perso")
    # df = hours_per_day(git_df)
    # df = merge_histories("perso")
    # import pandas as pd
    # pd.set_option('display.max_rows', None)
    # print(df)
    assert True

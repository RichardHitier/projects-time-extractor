from web.tools.histories import repo_to_df, hours_per_day, pomo_minutes, merge_histories, project_to_df, \
    daily_commits


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


def test_pomofocus_to_df():
    df = pomo_minutes("calipso")
    print(df)
    # assert len(df) == 58
    assert True


def test_merge_histories():
    df = merge_histories("calipso")
    import pandas as pd
    pd.set_option('display.max_rows', None)
    print(df)
    assert True


def test_merge_with_no_git():
    git_df = project_to_df("perso")
    # df = hours_per_day(git_df)
    # df = merge_histories("perso")
    # import pandas as pd
    # pd.set_option('display.max_rows', None)
    # print(df)
    assert True

# squash-history

옵시디언 등 자동 커밋 레포의 히스토리를 삼각부등식으로 정리하는 도구.

같은 방향의 진행은 하나로 합치고, 방향이 바뀐 지점은 보존.

## 설치

파일 하나(`squash_history.py`)만 있으면 됨. 표준 라이브러리만 사용.

### git alias (추천)

```bash
git config --global alias.squash-history '!python3 /절대경로/squash_history.py'
```

이후 어느 레포에서나:
```bash
git squash-history
```

### 셸 alias

```bash
alias squash-history='python3 /절대경로/squash_history.py'
```

## 사용법

```bash
squash-history                  # 자동으로 안전 범위 탐지 후 정리
squash-history --dry-run        # 결과 미리 보기
squash-history --dry-run -v     # 파일별 거리값도 출력
squash-history --base abc1234   # 특정 커밋 이후만
```

다른 브랜치가 있으면 merge-base 이후(현재 브랜치 전용 구간)만 자동으로 처리.

## 동작 원리

```
A → B → C  커밋이 있을 때

d(A,B) + d(B,C) == d(A,C)  →  B에서 방향 전환 없음  →  A에 흡수
d(A,B) + d(B,C)  > d(A,C)  →  B에서 방향 전환 있음  →  보존
```

A에서 C로 가는 비용이 B를 거쳐도 안 거쳐도 같으면,
B는 생략해도 정보 손실이 없다는 뜻.

d는 글자 단위 edit distance (LCS 기반).

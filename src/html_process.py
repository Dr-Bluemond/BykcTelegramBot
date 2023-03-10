"""
this function process html into telegram defined markup language
"""
import re
from typing import List
import bs4


def walk(node: bs4.PageElement, result: List[str]):
    if isinstance(node, bs4.Tag):
        if node.name == 'p':
            result.append('\n')
            walkChildren(node, result)
            result.append('\n')
        elif node.name in ['b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del']:
            # https://core.telegram.org/bots/update56kabdkb12ibuisabdubodbasbdaosd
            result.append(f'<{node.name}>')
            walkChildren(node, result)
            result.append(f'</{node.name}>')
        elif node.name == 'br':
            result.append('\n')
        else:
            walkChildren(node, result)
    elif isinstance(node, bs4.NavigableString):
        result.append(node.text)


def walkChildren(node: bs4.Tag, result: List[str]):
    for child in node.children:
        walk(child, result)


def remove_continuous_newline(text: str) -> str:
    return re.compile(r'\s(\n\s*)+').sub('\n\n', text)


def transform(s: str) -> str:
    node = bs4.BeautifulSoup(s, 'html.parser')
    result = []
    walk(node, result)
    result = ''.join(result).strip()
    result = remove_continuous_newline(result)
    return result


if __name__ == '__main__':
    x = transform(
        """<p><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">腾讯会议：</span></span><strong><span style="font-family: 黑体;">324-195-464</span></strong></p><p><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体"></span></span><br/></p><p><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">1、主讲人介绍： &nbsp;&nbsp;</span></span></p><p><strong><span style="font-family: 宋体;font-size: 16px;background: rgb(255, 255, 255)"><span style="font-family:宋体">吴斌荣：</span></span></strong><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">作家，编辑，策展人，出版副编审。儿童问题研究者，上海市宝山区作家协会副主席，魔仙堡女主，</span><span style="font-family:宋体">Ashtanga练习者。教育学学士，教师中高级职称。</span></span></p><p><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)">&nbsp;</span></p><p><strong><span style="font-family: 宋体;font-size: 16px;background: rgb(255, 255, 255)"><span style="font-family:宋体">咕咚</span></span></strong><strong><span style="font-family: 宋体;font-size: 16px;background: rgb(255, 255, 255)"><span style="font-family:宋体">：</span></span></strong><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">独立插画师，从事插画和绘本创作</span></span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">，以及儿童绘画教育</span></span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">。</span>2017年入围金风车国际青年插画家大赛。2019年</span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">作品《小红帽》</span></span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">入围韩国</span></span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">南怡岛</span></span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">插画绘本短名单，作品在韩国首尔展出。</span></span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">图画书</span></span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">作品《臭袜子不见了》荣获第二届</span><span style="font-family:宋体">“青铜葵花图画书奖” </span></span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">的</span></span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">“妙趣横生奖”。</span></span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">出版后入选</span><span style="font-family:宋体">2</span></span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)">021</span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">年度</span><span style="font-family:宋体">“童阅中国”原创好童书，入选2</span></span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)">021</span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">三叶草年度好童书评选</span></span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)">TOP100</span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">榜单。图画书作品《金绣娘》入选</span><span style="font-family:宋体">2</span></span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)">022</span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">年度</span><span style="font-family:宋体">“妈妈的选择｜中国原创好绘本”，入围第八届爱丽丝绘本奖书单和原创组短名单。</span></span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">目前已出版</span></span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">绘本《金绣娘》、</span></span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">《臭袜子不见了》、</span></span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">《食物的旅程》、</span></span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">《小心！病毒入侵》</span></span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">，在《看图说话》杂志发表《出发！去海岛寻宝》《了不起的岩石》《读懂一粒沙》《化石》等。即将出版绘本《恐龙之夜》、《担心养不活却养活了自己的小猪》。</span></span></p><p><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)">&nbsp;</span></p><p><strong><span style="font-family: 宋体;font-size: 16px;background: rgb(255, 255, 255)"><span style="font-family:宋体">2、讲座内容：</span></span></strong></p><p><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">绘本中的民俗记忆与叙事重构</span></span></p><p><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">非遗</span><span style="font-family:宋体">·绘本·儿童·市场 童书编辑的工作</span></span></p><p><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">当下绘本领域的创作者、从业者和研究者正从</span><span style="font-family:宋体">“引进绘本”的热潮，开始朝向“本土绘本”聚焦，大家共同关注的焦点是：中国传统文化如何恰当地融入当下“本土绘本”创作</span></span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">。</span></span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">本讲座以</span>2022年出版的非遗传承绘本《金绣娘》为例，从田野调查（采风）、文本故事创作、图像故事创作三个方面，来探讨作为传统文化的民俗记忆如何通过文本和图像的双重叙事重构，转化为适合儿童阅读的绘本。此外，绘本不是创作者个人</span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">的</span></span><span style=";font-family:宋体;font-size:16px;background:rgb(255,255,255)"><span style="font-family:宋体">产物，而是团队合作的产物。一本面世的绘本，不只是创作者个人努力的结果，后期的装帧设计、排版印刷、宣传发行等等环节，都凝聚着一个团队的力量。</span></span></p><p><br/></p>""")
    print(x)
